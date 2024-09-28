# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import dataclasses
import email.message
import email.policy
import email.utils
import enum
import os
import os.path
import pathlib
import re
import sys
import typing
import warnings

from . import constants
from .errors import ConfigurationError, ConfigurationWarning, ErrorCollector
from .pyproject import License, PyProjectReader, Readme


if typing.TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from packaging.requirements import Requirement

    if sys.version_info < (3, 11):
        from typing_extensions import Self
    else:
        from typing import Self

    from .project_table import PyProjectTable

import packaging.markers
import packaging.specifiers
import packaging.utils
import packaging.version


__version__ = '0.9.0b5'

__all__ = [
    'ConfigurationError',
    'ConfigurationWarning',
    'License',
    'RFC822Message',
    'RFC822Policy',
    'Readme',
    'StandardMetadata',
    'field_to_metadata',
    'Validate',
]


def __dir__() -> list[str]:
    return __all__


class Validate(enum.Flag):
    TOP_LEVEL = enum.auto()
    BUILD_SYSTEM = enum.auto()
    PROJECT = enum.auto()
    WARN = enum.auto()
    ALL = TOP_LEVEL | BUILD_SYSTEM | PROJECT
    NONE = 0


def field_to_metadata(field: str) -> frozenset[str]:
    """
    Return the METADATA fields that correspond to a project field.
    """
    return frozenset(constants.PROJECT_TO_METADATA[field])


@dataclasses.dataclass
class _SmartMessageSetter:
    """
    This provides a nice internal API for setting values in an Message to
    reduce boilerplate.

    If a value is None, do nothing.
    If a value contains a newline, indent it (may produce a warning in the future).
    """

    message: email.message.Message

    def __setitem__(self, name: str, value: str | None) -> None:
        if not value:
            return
        self.message[name] = value

    def set_payload(self, payload: str) -> None:
        self.message.set_payload(payload)


@dataclasses.dataclass
class _JSonMessageSetter:
    """
    This provides an API to build a JSON message output. Line breaks are
    preserved this way.
    """

    data: dict[str, str | list[str]]

    def __setitem__(self, name: str, value: str | None) -> None:
        name = name.lower()
        key = name.replace('-', '_')

        if value is None:
            return

        if name == 'keywords':
            values = (x.strip() for x in value.split(','))
            self.data[key] = [x for x in values if x]
        elif name in constants.KNOWN_MULTIUSE:
            entry = self.data.setdefault(key, [])
            assert isinstance(entry, list)
            entry.append(value)
        else:
            self.data[key] = value

    def set_payload(self, payload: str) -> None:
        self['description'] = payload


class RFC822Policy(email.policy.EmailPolicy):
    """
    This is `email.policy.EmailPolicy`, but with a simple ``header_store_parse``
    implementation that handles multiline values, and some nice defaults.
    """

    utf8 = True
    mangle_from_ = False
    max_line_length = 0

    def header_store_parse(self, name: str, value: str) -> tuple[str, str]:
        if name.lower() not in constants.KNOWN_METADATA_FIELDS:
            msg = f'Unknown field "{name}"'
            raise ConfigurationError(msg, key=name)
        size = len(name) + 2
        value = value.replace('\n', '\n' + ' ' * size)
        return (name, value)


class RFC822Message(email.message.EmailMessage):
    """
    This is `email.message.EmailMessage` with two small changes: it defaults to
    our `RFC822Policy`, and it correctly writes unicode when being called
    with `bytes()`.
    """

    def __init__(self) -> None:
        super().__init__(policy=RFC822Policy())

    def as_bytes(
        self, unixfrom: bool = False, policy: email.policy.Policy | None = None
    ) -> bytes:
        return self.as_string(unixfrom, policy=policy).encode('utf-8')


@dataclasses.dataclass
class StandardMetadata:
    name: str
    version: packaging.version.Version | None = None
    description: str | None = None
    license: License | str | None = None
    license_files: list[pathlib.Path] | None = None
    readme: Readme | None = None
    requires_python: packaging.specifiers.SpecifierSet | None = None
    dependencies: list[Requirement] = dataclasses.field(default_factory=list)
    optional_dependencies: dict[str, list[Requirement]] = dataclasses.field(
        default_factory=dict
    )
    entrypoints: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)
    authors: list[tuple[str, str | None]] = dataclasses.field(default_factory=list)
    maintainers: list[tuple[str, str | None]] = dataclasses.field(default_factory=list)
    urls: dict[str, str] = dataclasses.field(default_factory=dict)
    classifiers: list[str] = dataclasses.field(default_factory=list)
    keywords: list[str] = dataclasses.field(default_factory=list)
    scripts: dict[str, str] = dataclasses.field(default_factory=dict)
    gui_scripts: dict[str, str] = dataclasses.field(default_factory=dict)
    dynamic: list[str] = dataclasses.field(default_factory=list)
    """
    This field is used to track dynamic fields. You can't set a field not in this list.
    """
    dynamic_metadata: list[str] = dataclasses.field(default_factory=list)
    """
    This is a list of METADATA fields that can change inbetween SDist and wheel. Requires metadata_version 2.2+.
    """

    metadata_version: str | None = None
    all_errors: bool = False
    _locked_metadata: bool = False

    def __post_init__(self) -> None:
        self.validate()

    def __setattr__(self, name: str, value: Any) -> None:
        if self._locked_metadata and name.replace('_', '-') not in set(self.dynamic) | {
            'metadata-version',
            'dynamic-metadata',
        }:
            msg = f'Field "{name}" is not dynamic'
            raise AttributeError(msg)
        super().__setattr__(name, value)

    def validate(self, *, warn: bool = True) -> None:  # noqa: C901
        errors = ErrorCollector(collect_errors=self.all_errors)

        if self.auto_metadata_version not in constants.KNOWN_METADATA_VERSIONS:
            msg = f'The metadata_version must be one of {constants.KNOWN_METADATA_VERSIONS} or None (default)'
            errors.config_error(msg)

        # See https://packaging.python.org/en/latest/specifications/core-metadata/#name and
        # https://packaging.python.org/en/latest/specifications/name-normalization/#name-format
        if not re.match(
            r'^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$', self.name, re.IGNORECASE
        ):
            msg = (
                f'Invalid project name "{self.name}". A valid name consists only of ASCII letters and '
                'numbers, period, underscore and hyphen. It must start and end with a letter or number'
            )
            errors.config_error(msg, key='project.name')

        if self.license_files is not None and isinstance(self.license, License):
            msg = '"project.license-files" must not be used when "project.license" is not a SPDX license expression'
            errors.config_error(msg, key='project.license-files')

        if isinstance(self.license, str) and any(
            c.startswith('License ::') for c in self.classifiers
        ):
            msg = 'Setting "project.license" to an SPDX license expression is not compatible with "License ::" classifiers'
            errors.config_error(msg, key='project.license')

        if warn:
            if self.description and '\n' in self.description:
                warnings.warn(
                    'The one-line summary "project.description" should not contain more than one line. Readers might merge or truncate newlines.',
                    ConfigurationWarning,
                    stacklevel=2,
                )
            if self.auto_metadata_version not in constants.PRE_SPDX_METADATA_VERSIONS:
                if isinstance(self.license, License):
                    warnings.warn(
                        'Set "project.license" to an SPDX license expression for metadata >= 2.4',
                        ConfigurationWarning,
                        stacklevel=2,
                    )
                elif any(c.startswith('License ::') for c in self.classifiers):
                    warnings.warn(
                        '"License ::" classifiers are deprecated for metadata >= 2.4, use a SPDX license expression for "project.license" instead',
                        ConfigurationWarning,
                        stacklevel=2,
                    )

        if (
            isinstance(self.license, str)
            and self.auto_metadata_version in constants.PRE_SPDX_METADATA_VERSIONS
        ):
            msg = 'Setting "project.license" to an SPDX license expression is supported only when emitting metadata version >= 2.4'
            errors.config_error(msg, key='project.license')

        if (
            self.license_files is not None
            and self.auto_metadata_version in constants.PRE_SPDX_METADATA_VERSIONS
        ):
            msg = '"project.license-files" is supported only when emitting metadata version >= 2.4'
            errors.config_error(msg, key='project.license-files')

        errors.finalize('Metadata validation failed')

    @property
    def auto_metadata_version(self) -> str:
        if self.metadata_version is not None:
            return self.metadata_version

        if isinstance(self.license, str) or self.license_files is not None:
            return '2.4'
        if self.dynamic_metadata:
            return '2.2'
        return '2.1'

    @property
    def canonical_name(self) -> str:
        return packaging.utils.canonicalize_name(self.name)

    @classmethod
    def from_pyproject(  # noqa: C901
        cls,
        data: Mapping[str, Any],
        project_dir: str | os.PathLike[str] = os.path.curdir,
        metadata_version: str | None = None,
        dynamic_metadata: list[str] | None = None,
        *,
        validate: Validate = Validate.WARN,
        all_errors: bool = False,
    ) -> Self:
        pyproject = PyProjectReader(collect_errors=all_errors)

        pyproject_table: PyProjectTable = data  # type: ignore[assignment]
        if 'project' not in pyproject_table:
            msg = 'Section "project" missing in pyproject.toml'
            pyproject.config_error(msg, key='project')
            pyproject.finalize('Failed to parse pyproject.toml')
            msg = 'Unreachable code'  # pragma: no cover
            raise AssertionError(msg)  # pragma: no cover

        project = pyproject_table['project']
        project_dir = pathlib.Path(project_dir)

        if Validate.TOP_LEVEL | Validate.WARN & validate:
            extra_keys = set(pyproject_table) - constants.KNOWN_TOPLEVEL_FIELDS
            if extra_keys:
                extra_keys_str = ', '.join(sorted(f'"{k}"' for k in extra_keys))
                msg = f'Extra keys present in pyproject.toml: {extra_keys_str}'
                if Validate.TOP_LEVEL in validate:
                    pyproject.config_error(msg)
                elif Validate.WARN in validate:
                    warnings.warn(msg, ConfigurationWarning, stacklevel=2)

        if Validate.BUILD_SYSTEM | Validate.WARN & validate:
            extra_keys = (
                set(pyproject_table.get('build-system', {}))
                - constants.KNOWN_BUILD_SYSTEM_FIELDS
            )
            if extra_keys:
                extra_keys_str = ', '.join(sorted(f'"{k}"' for k in extra_keys))
                msg = f'Extra keys present in "build-system": {extra_keys_str}'
                if Validate.BUILD_SYSTEM in validate:
                    pyproject.config_error(msg)
                elif Validate.WARN in validate:
                    warnings.warn(msg, ConfigurationWarning, stacklevel=2)

        if Validate.PROJECT | Validate.WARN & validate:
            extra_keys = set(project) - constants.KNOWN_PROJECT_FIELDS
            if extra_keys:
                extra_keys_str = ', '.join(sorted(f'"{k}"' for k in extra_keys))
                msg = f'Extra keys present in "project": {extra_keys_str}'
                if Validate.PROJECT in validate:
                    pyproject.config_error(msg)
                elif Validate.WARN in validate:
                    warnings.warn(msg, ConfigurationWarning, stacklevel=2)

        dynamic = pyproject.get_dynamic(project)

        for field in dynamic:
            if field in data['project']:
                msg = f'Field "project.{field}" declared as dynamic in "project.dynamic" but is defined'
                pyproject.config_error(msg, key=field)

        raw_name = project.get('name')
        name = 'UNKNOWN'
        if raw_name is None:
            msg = 'Field "project.name" missing'
            pyproject.config_error(msg, key='name')
        else:
            tmp_name = pyproject.ensure_str(raw_name, 'project.name')
            if tmp_name is not None:
                name = tmp_name

        version: packaging.version.Version | None = packaging.version.Version('0.0.0')
        raw_version = project.get('version')
        if raw_version is not None:
            version_string = pyproject.ensure_str(raw_version, 'project.version')
            if version_string is not None:
                with pyproject.collect():
                    version = (
                        packaging.version.Version(version_string)
                        if version_string
                        else None
                    )
        elif 'version' not in dynamic:
            msg = 'Field "project.version" missing and "version" not specified in "project.dynamic"'
            pyproject.config_error(msg, key='version')

        # Description fills Summary, which cannot be multiline
        # However, throwing an error isn't backward compatible,
        # so leave it up to the users for now.
        project_description_raw = project.get('description')
        description = (
            pyproject.ensure_str(project_description_raw, 'project.description')
            if project_description_raw is not None
            else None
        )

        requires_python_raw = project.get('requires-python')
        requires_python = None
        if requires_python_raw is not None:
            requires_python_string = pyproject.ensure_str(
                requires_python_raw, 'project.requires-python'
            )
            if requires_python_string is not None:
                with pyproject.collect():
                    requires_python = packaging.specifiers.SpecifierSet(
                        requires_python_string
                    )

        self = None
        with pyproject.collect():
            self = cls(
                name=name,
                version=version,
                description=description,
                license=pyproject.get_license(project, project_dir),
                license_files=pyproject.get_license_files(project, project_dir),
                readme=pyproject.get_readme(project, project_dir),
                requires_python=requires_python,
                dependencies=pyproject.get_dependencies(project),
                optional_dependencies=pyproject.get_optional_dependencies(project),
                entrypoints=pyproject.get_entrypoints(project),
                authors=pyproject.ensure_people(
                    project.get('authors', []), 'project.authors'
                ),
                maintainers=pyproject.ensure_people(
                    project.get('maintainers', []), 'project.maintainers'
                ),
                urls=pyproject.ensure_dict(project.get('urls', {}), 'project.urls')
                or {},
                classifiers=pyproject.ensure_list(
                    project.get('classifiers', []), 'project.classifiers'
                )
                or [],
                keywords=pyproject.ensure_list(
                    project.get('keywords', []), 'project.keywords'
                )
                or [],
                scripts=pyproject.ensure_dict(
                    project.get('scripts', {}), 'project.scripts'
                )
                or {},
                gui_scripts=pyproject.ensure_dict(
                    project.get('gui-scripts', {}), 'project.gui-scripts'
                )
                or {},
                dynamic=dynamic,
                dynamic_metadata=dynamic_metadata or [],
                metadata_version=metadata_version,
                all_errors=all_errors,
            )
            self._locked_metadata = True

        pyproject.finalize('Failed to parse pyproject.toml')
        assert self is not None
        return self

    def as_rfc822(self) -> RFC822Message:
        message = RFC822Message()
        smart_message = _SmartMessageSetter(message)
        self._write_metadata(smart_message)
        return message

    def as_json(self) -> dict[str, str | list[str]]:
        message: dict[str, str | list[str]] = {}
        smart_message = _JSonMessageSetter(message)
        self._write_metadata(smart_message)
        return message

    def _write_metadata(  # noqa: C901
        self, smart_message: _SmartMessageSetter | _JSonMessageSetter
    ) -> None:
        self.validate(warn=False)

        smart_message['Metadata-Version'] = self.auto_metadata_version
        smart_message['Name'] = self.name
        if not self.version:
            msg = 'Missing version field'
            raise ConfigurationError(msg)
        smart_message['Version'] = str(self.version)
        # skip 'Platform'
        # skip 'Supported-Platform'
        if self.description:
            smart_message['Summary'] = self.description
        smart_message['Keywords'] = ','.join(self.keywords) or None
        if 'homepage' in self.urls:
            smart_message['Home-page'] = self.urls['homepage']
        # skip 'Download-URL'
        smart_message['Author'] = self._name_list(self.authors)
        smart_message['Author-Email'] = self._email_list(self.authors)
        smart_message['Maintainer'] = self._name_list(self.maintainers)
        smart_message['Maintainer-Email'] = self._email_list(self.maintainers)

        if isinstance(self.license, License):
            smart_message['License'] = self.license.text
        elif isinstance(self.license, str):
            smart_message['License-Expression'] = self.license

        if self.license_files is not None:
            for license_file in sorted(set(self.license_files)):
                smart_message['License-File'] = os.fspath(license_file.as_posix())

        for classifier in self.classifiers:
            smart_message['Classifier'] = classifier
        # skip 'Provides-Dist'
        # skip 'Obsoletes-Dist'
        # skip 'Requires-External'
        for name, url in self.urls.items():
            smart_message['Project-URL'] = f'{name.capitalize()}, {url}'
        if self.requires_python:
            smart_message['Requires-Python'] = str(self.requires_python)
        for dep in self.dependencies:
            smart_message['Requires-Dist'] = str(dep)
        for extra, requirements in self.optional_dependencies.items():
            norm_extra = extra.replace('.', '-').replace('_', '-').lower()
            smart_message['Provides-Extra'] = norm_extra
            for requirement in requirements:
                smart_message['Requires-Dist'] = str(
                    self._build_extra_req(norm_extra, requirement)
                )
        if self.readme:
            if self.readme.content_type:
                smart_message['Description-Content-Type'] = self.readme.content_type
            smart_message.set_payload(self.readme.text)
        # Core Metadata 2.2
        if self.auto_metadata_version != '2.1':
            for field in self.dynamic_metadata:
                if field.lower() in {'name', 'version', 'dynamic'}:
                    msg = f'Field cannot be set as dynamic metadata: {field}'
                    raise ConfigurationError(msg)
                if field.lower() not in constants.KNOWN_METADATA_FIELDS:
                    msg = f'Field is not known: {field}'
                    raise ConfigurationError(msg)
                smart_message['Dynamic'] = field

    def _name_list(self, people: list[tuple[str, str | None]]) -> str | None:
        return ', '.join(name for name, email_ in people if not email_) or None

    def _email_list(self, people: list[tuple[str, str | None]]) -> str | None:
        return (
            ', '.join(
                email.utils.formataddr((name, _email))
                for name, _email in people
                if _email
            )
            or None
        )

    def _build_extra_req(
        self,
        extra: str,
        requirement: Requirement,
    ) -> Requirement:
        # append or add our extra marker
        requirement = copy.copy(requirement)
        if requirement.marker:
            if 'or' in requirement.marker._markers:
                requirement.marker = packaging.markers.Marker(
                    f'({requirement.marker}) and extra == "{extra}"'
                )
            else:
                requirement.marker = packaging.markers.Marker(
                    f'{requirement.marker} and extra == "{extra}"'
                )
        else:
            requirement.marker = packaging.markers.Marker(f'extra == "{extra}"')
        return requirement
