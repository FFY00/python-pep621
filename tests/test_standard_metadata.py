# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import pathlib
import re
import shutil
import sys
import textwrap
import warnings

import packaging.specifiers
import packaging.version
import pytest

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib

import pyproject_metadata
import pyproject_metadata.constants

DIR = pathlib.Path(__file__).parent.resolve()


try:
    import exceptiongroup
except ImportError:
    exceptiongroup = None  # type: ignore[assignment]


@pytest.fixture(params=pyproject_metadata.constants.KNOWN_METADATA_VERSIONS)
def metadata_version(request: pytest.FixtureRequest) -> str:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(params=["one_error", "all_errors", "exceptiongroup"])
def all_errors(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    param: str = request.param
    if param == "exceptiongroup":
        if exceptiongroup is None:
            pytest.skip("exceptiongroup is not installed")
        monkeypatch.setattr(
            pyproject_metadata.errors, "ExceptionGroup", exceptiongroup.ExceptionGroup
        )
    return param != "one_error"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        pytest.param(
            "",
            'Section "project" missing in pyproject.toml',
            id="Missing project section",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
            """,
            'Field "project.name" has an invalid type, expecting a string (got bool)',
            id="Invalid name type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                not-real-key = true
            """,
            "Extra keys present in \"project\": 'not-real-key'",
            id="Invalid project key",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dynamic = [
                    "name",
                ]
            """,
            "Unsupported field 'name' in \"project.dynamic\"",
            id="Unsupported field in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dynamic = [
                    3,
                ]
            """,
            'Field "project.dynamic" contains item with invalid type, expecting a string (got int)',
            id="Unsupported type in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = true
            """,
            'Field "project.version" has an invalid type, expecting a string (got bool)',
            id="Invalid version type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
            """,
            'Field "project.version" missing and \'version\' not specified in "project.dynamic"',
            id="Missing version",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0-extra"
            """,
            "Invalid \"project.version\" value, expecting a valid PEP 440 version (got '0.1.0-extra')",
            id="Invalid version value",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = true
            """,
            'Field "project.license" has an invalid type, expecting a string or table of strings (got bool)',
            id="License invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = {}
            """,
            'Invalid "project.license" contents, expecting a string or one key "file" or "text" (got {})',
            id="Missing license keys",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = "...", text = "..." }
            """,
            (
                'Invalid "project.license" contents, expecting a string or one key "file" or "text"'
                " (got {'file': '...', 'text': '...'})"
            ),
            id="Both keys for license",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { made-up = ":(" }
            """,
            'Unexpected field "project.license.made-up"',
            id="Got made-up license field",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = true }
            """,
            'Field "project.license.file" has an invalid type, expecting a string (got bool)',
            id="Invalid type for license.file",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { text = true }
            """,
            'Field "project.license.text" has an invalid type, expecting a string (got bool)',
            id="Invalid type for license.text",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = { file = "this-file-does-not-exist" }
            """,
            "License file not found ('this-file-does-not-exist')",
            id="License file not present",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = true
            """,
            (
                'Field "project.readme" has an invalid type, expecting either '
                "a string or table of strings (got bool)"
            ),
            id="Invalid readme type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = {}
            """,
            'Invalid "project.readme" contents, expecting either "file" or "text" (got {})',
            id="Empty readme table",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
            """,
            "Could not infer content type for readme file 'README.jpg'",
            id="Unsupported filename in readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "...", text = "..." }
            """,
            (
                'Invalid "project.readme" contents, expecting either "file" or "text"'
                " (got {'file': '...', 'text': '...'})"
            ),
            id="Both readme fields",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { made-up = ":(" }
            """,
            'Unexpected field "project.readme.made-up"',
            id="Unexpected field in readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = true }
            """,
            'Field "project.readme.file" has an invalid type, expecting a string (got bool)',
            id="Invalid type for readme.file",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { text = true }
            """,
            'Field "project.readme.text" has an invalid type, expecting a string (got bool)',
            id="Invalid type for readme.text",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "this-file-does-not-exist", content-type = "..." }
            """,
            "Readme file not found ('this-file-does-not-exist')",
            id="Readme file not present",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = "README.md" }
            """,
            'Field "project.readme.content-type" missing',
            id="Missing content-type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { file = 'README.md', content-type = true }
            """,
            'Field "project.readme.content-type" has an invalid type, expecting a string (got bool)',
            id="Wrong content-type type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                readme = { text = "..." }
            """,
            'Field "project.readme.content-type" missing',
            id="Missing content-type for readme",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                description = true
            """,
            'Field "project.description" has an invalid type, expecting a string (got bool)',
            id="Invalid description type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = "some string!"
            """,
            'Field "project.dependencies" has an invalid type, expecting a list of strings (got str)',
            id="Invalid dependencies type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = [
                    99,
                ]
            """,
            'Field "project.dependencies" contains item with invalid type, expecting a string (got int)',
            id="Invalid dependencies item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                dependencies = [
                    "definitely not a valid PEP 508 requirement!",
                ]
            """,
            (
                'Field "project.dependencies" contains an invalid PEP 508 requirement '
                "string 'definitely not a valid PEP 508 requirement!' "
            ),
            id="Invalid dependencies item",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                optional-dependencies = true
            """,
            (
                'Field "project.optional-dependencies" has an invalid type, '
                "expecting a table of PEP 508 requirement strings (got bool)"
            ),
            id="Invalid optional-dependencies type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = "some string!"
            """,
            (
                'Field "project.optional-dependencies.test" has an invalid type, '
                "expecting a table of PEP 508 requirement strings (got str)"
            ),
            id="Invalid optional-dependencies not list",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = [
                    true,
                ]
            """,
            (
                'Field "project.optional-dependencies.test" has an invalid type, '
                "expecting a PEP 508 requirement string (got bool)"
            ),
            id="Invalid optional-dependencies item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.optional-dependencies]
                test = [
                    "definitely not a valid PEP 508 requirement!",
                ]
            """,
            (
                'Field "project.optional-dependencies.test" contains an invalid '
                "PEP 508 requirement string 'definitely not a valid PEP 508 requirement!' "
            ),
            id="Invalid optional-dependencies item",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                default-optional-dependency-keys = ["none"]
                [project.optional-dependencies]
                test = [
                    "a",
                ]
            """,
            (
                'Field "project.default-optional-dependency-keys" contains keys '
                "not in \"project.optional-dependencies\": {'none'}"
            ),
            id="Invalid default-optional-dependency-keys item",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                default-optional-dependency-keys = ["none"]
            """,
            (
                'Field "project.default-optional-dependency-keys" contains keys '
                "not in \"project.optional-dependencies\": {'none'}"
            ),
            id="Invalid default-optional-dependency-keys item without optional-dependencies",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                default-optional-dependency-keys = [1]
            """,
            (
                'Field "project.default-optional-dependency-keys" contains item with invalid '
                "type, expecting a string (got int)"
            ),
            id="Invalid default-optional-dependency-keys item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                default-optional-dependency-keys = "test"
                [project.optional-dependencies]
                test = [
                    "a",
                ]
            """,
            (
                'Field "project.default-optional-dependency-keys" has an invalid type, '
                "expecting a list of strings (got str)"
            ),
            id="Invalid default-optional-dependency-keys not list",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                requires-python = true
            """,
            'Field "project.requires-python" has an invalid type, expecting a string (got bool)',
            id="Invalid requires-python type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                requires-python = "3.8"
            """,
            "Invalid \"project.requires-python\" value, expecting a valid specifier set (got '3.8')",
            id="Invalid requires-python value",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = "some string!"
            """,
            'Field "project.keywords" has an invalid type, expecting a list of strings (got str)',
            id="Invalid keywords type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = [3]
            """,
            'Field "project.keywords" contains item with invalid type, expecting a string (got int)',
            id="Invalid keyword type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                keywords = [
                    true,
                ]
            """,
            'Field "project.keywords" contains item with invalid type, expecting a string (got bool)',
            id="Invalid keywords item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                authors = {}
            """,
            (
                'Field "project.authors" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got dict)'
            ),
            id="Invalid authors type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                authors = [
                    true,
                ]
            """,
            (
                'Field "project.authors" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with bool)'
            ),
            id="Invalid authors item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = {}
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got dict)'
            ),
            id="Invalid maintainers type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    10
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with int)'
            ),
            id="Invalid maintainers item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    {"name" = 12}
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with dict with int)'
            ),
            id="Invalid maintainers nested type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                maintainers = [
                    {"name" = "me", "other" = "you"}
                ]
            """,
            (
                'Field "project.maintainers" has an invalid type, expecting a list of '
                'tables containing the "name" and/or "email" keys (got list with dict with extra keys "other")'
            ),
            id="Invalid maintainers nested type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = "some string!"
            """,
            'Field "project.classifiers" has an invalid type, expecting a list of strings (got str)',
            id="Invalid classifiers type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = [
                    true,
                ]
            """,
            'Field "project.classifiers" contains item with invalid type, expecting a string (got bool)',
            id="Invalid classifiers item type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                homepage = true
            """,
            'Field "project.urls.homepage" has an invalid type, expecting a string (got bool)',
            id="Invalid urls homepage type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                Documentation = true
            """,
            'Field "project.urls.Documentation" has an invalid type, expecting a string (got bool)',
            id="Invalid urls documentation type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                repository = true
            """,
            'Field "project.urls.repository" has an invalid type, expecting a string (got bool)',
            id="Invalid urls repository type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                "I am really really too long for this place" = "url"
            """,
            "\"project.urls\" names cannot be more than 32 characters long (got 'I am really really too long for this place')",
            id="URL name too long",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.urls]
                changelog = true
            """,
            'Field "project.urls.changelog" has an invalid type, expecting a string (got bool)',
            id="Invalid urls changelog type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                scripts = []
            """,
            'Field "project.scripts" has an invalid type, expecting a table of strings (got list)',
            id="Invalid scripts type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                gui-scripts = []
            """,
            'Field "project.gui-scripts" has an invalid type, expecting a table of strings (got list)',
            id="Invalid gui-scripts type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                entry-points = []
            """,
            (
                'Field "project.entry-points" has an invalid type, '
                "expecting a table of entrypoint sections (got list)"
            ),
            id="Invalid entry-points type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                entry-points = { section = "something" }
            """,
            (
                'Field "project.entry-points.section" has an invalid type, '
                "expecting a table of entrypoints (got str)"
            ),
            id="Invalid entry-points section type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.entry-points.section]
                entrypoint = []
            """,
            'Field "project.entry-points.section.entrypoint" has an invalid type, expecting a string (got list)',
            id="Invalid entry-points entrypoint type",
        ),
        pytest.param(
            """
                [project]
                name = ".test"
                version = "0.1.0"
            """,
            (
                "Invalid project name '.test'. A valid name consists only of ASCII letters and "
                "numbers, period, underscore and hyphen. It must start and end with a letter or number"
            ),
            id="Invalid project name",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                [project.entry-points.bad-name]
            """,
            (
                'Field "project.entry-points" has an invalid value, expecting a name containing only '
                "alphanumeric, underscore, or dot characters (got 'bad-name')"
            ),
            id="Invalid entry-points name",
        ),
        # both license files and classic license are not allowed
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = []
                license.text = 'stuff'
            """,
            '"project.license-files" must not be used when "project.license" is not a SPDX license expression',
            id="Both license files and classic license",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['../LICENSE']
            """,
            "'../LICENSE' is an invalid \"project.license-files\" glob: the pattern must match files within the project directory",
            id="Parent license-files glob",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = [12]
            """,
            'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
            id="Parent license-files invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['this', 12]
            """,
            'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
            id="Parent license-files invalid type",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['/LICENSE']
            """,
            "'/LICENSE' is an invalid \"project.license-files\" glob: the pattern must match files within the project directory",
            id="Absolute license-files glob",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = 'MIT'
                classifiers = ['License :: OSI Approved :: MIT License']
            """,
            "Setting \"project.license\" to an SPDX license expression is not compatible with 'License ::' classifiers",
            id="SPDX license and License trove classifiers",
        ),
    ],
)
def test_load(
    data: str, error: str, monkeypatch: pytest.MonkeyPatch, all_errors: bool
) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")
    if not all_errors:
        with pytest.raises(
            pyproject_metadata.ConfigurationError, match=re.escape(error)
        ):
            pyproject_metadata.StandardMetadata.from_pyproject(
                tomllib.loads(textwrap.dedent(data)),
                allow_extra_keys=False,
            )
    else:
        with warnings.catch_warnings():
            warnings.simplefilter(
                action="ignore", category=pyproject_metadata.errors.ConfigurationWarning
            )
            with pytest.raises(pyproject_metadata.errors.ExceptionGroup) as execinfo:
                pyproject_metadata.StandardMetadata.from_pyproject(
                    tomllib.loads(textwrap.dedent(data)),
                    allow_extra_keys=False,
                    all_errors=True,
                )
        exceptions = execinfo.value.exceptions
        args = [e.args[0] for e in exceptions]
        assert len(args) == 1
        assert error in args[0]
        assert "Failed to parse pyproject.toml" in repr(execinfo.value)


@pytest.mark.parametrize(
    ("data", "errors"),
    [
        pytest.param(
            "[project]",
            [
                'Field "project.name" missing',
                'Field "project.version" missing and \'version\' not specified in "project.dynamic"',
            ],
            id="Missing project name",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
                dynamic = [
                    "name",
                ]
            """,
            [
                "Unsupported field 'name' in \"project.dynamic\"",
                'Field "project.name" has an invalid type, expecting a string (got bool)',
            ],
            id="Unsupported field in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = true
                version = "0.1.0"
                dynamic = [
                    3,
                ]
            """,
            [
                'Field "project.dynamic" contains item with invalid type, expecting a string (got int)',
                'Field "project.name" has an invalid type, expecting a string (got bool)',
            ],
            id="Unsupported type in project.dynamic",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
                license-files = [12]
            """,
            [
                'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
                "Could not infer content type for readme file 'README.jpg'",
            ],
            id="Unsupported filename in readme",
        ),
        pytest.param(
            """
                [project]
                name = 'test'
                version = "0.1.0"
                readme = "README.jpg"
                license-files = [12]
                entry-points.bad-name = {}
                other-entry = {}
                not-valid = true
            """,
            [
                "Extra keys present in \"project\": 'not-valid', 'other-entry'",
                'Field "project.license-files" contains item with invalid type, expecting a string (got int)',
                "Could not infer content type for readme file 'README.jpg'",
                "Field \"project.entry-points\" has an invalid value, expecting a name containing only alphanumeric, underscore, or dot characters (got 'bad-name')",
            ],
            id="Four errors including extra keys",
        ),
    ],
)
def test_load_multierror(
    data: str, errors: list[str], monkeypatch: pytest.MonkeyPatch, all_errors: bool
) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")
    if not all_errors:
        with pytest.raises(
            pyproject_metadata.ConfigurationError, match=re.escape(errors[0])
        ):
            pyproject_metadata.StandardMetadata.from_pyproject(
                tomllib.loads(textwrap.dedent(data)),
                allow_extra_keys=False,
            )
    else:
        with warnings.catch_warnings():
            warnings.simplefilter(
                action="ignore", category=pyproject_metadata.errors.ConfigurationWarning
            )
            with pytest.raises(pyproject_metadata.errors.ExceptionGroup) as execinfo:
                pyproject_metadata.StandardMetadata.from_pyproject(
                    tomllib.loads(textwrap.dedent(data)),
                    allow_extra_keys=False,
                    all_errors=True,
                )
        exceptions = execinfo.value.exceptions
        args = [e.args[0] for e in exceptions]
        assert len(args) == len(errors)
        assert args == errors
        assert "Failed to parse pyproject.toml" in repr(execinfo.value)


@pytest.mark.parametrize(
    ("data", "error", "metadata_version"),
    [
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license = 'MIT'
            """,
            'Setting "project.license" to an SPDX license expression is supported only when emitting metadata version >= 2.4',
            "2.3",
            id="SPDX with metadata_version 2.3",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license-files = ['README.md']
            """,
            '"project.license-files" is supported only when emitting metadata version >= 2.4',
            "2.3",
            id="license-files with metadata_version 2.3",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                default-optional-dependency-keys = []
            """,
            '"project.default-optional-dependency-keys" is supported only when emitting metadata version >= 2.6',
            "2.5",
            id=" with metadata_version 2.5",
        ),
    ],
)
def test_load_with_metadata_version(
    data: str, error: str, metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")
    with pytest.raises(pyproject_metadata.ConfigurationError, match=re.escape(error)):
        pyproject_metadata.StandardMetadata.from_pyproject(
            tomllib.loads(textwrap.dedent(data)), metadata_version=metadata_version
        )


@pytest.mark.parametrize(
    ("data", "error", "metadata_version"),
    [
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                license.text = 'MIT'
            """,
            'Set "project.license" to an SPDX license expression for metadata >= 2.4',
            "2.4",
            id="Classic license with metadata 2.4",
        ),
        pytest.param(
            """
                [project]
                name = "test"
                version = "0.1.0"
                classifiers = ['License :: OSI Approved :: MIT License']
            """,
            "'License ::' classifiers are deprecated for metadata >= 2.4, use a SPDX license expression for \"project.license\" instead",
            "2.4",
            id="License trove classifiers with metadata 2.4",
        ),
    ],
)
def test_load_with_metadata_version_warnings(
    data: str, error: str, metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")
    with pytest.warns(
        pyproject_metadata.errors.ConfigurationWarning, match=re.escape(error)
    ):
        pyproject_metadata.StandardMetadata.from_pyproject(
            tomllib.loads(textwrap.dedent(data)), metadata_version=metadata_version
        )


@pytest.mark.parametrize("after_rfc", [False, True])
def test_value(after_rfc: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")
    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))

    if after_rfc:
        metadata.as_rfc822()

    assert metadata.dynamic == []
    assert metadata.name == "full_metadata"
    assert metadata.canonical_name == "full-metadata"
    assert metadata.version == packaging.version.Version("3.2.1")
    assert metadata.requires_python == packaging.specifiers.Specifier(">=3.8")
    assert isinstance(metadata.license, pyproject_metadata.License)
    assert metadata.license.file is None
    assert metadata.license.text == "some license text"
    assert isinstance(metadata.readme, pyproject_metadata.Readme)
    assert metadata.readme.file == pathlib.Path("README.md")
    assert metadata.readme.text == pathlib.Path("README.md").read_text(encoding="utf-8")
    assert metadata.readme.content_type == "text/markdown"
    assert metadata.description == "A package with all the metadata :)"
    assert metadata.authors == [
        ("Unknown", "example@example.com"),
        ("Example!", None),
    ]
    assert metadata.maintainers == [
        ("Other Example", "other@example.com"),
    ]
    assert metadata.keywords == ["trampolim", "is", "interesting"]
    assert metadata.classifiers == [
        "Development Status :: 4 - Beta",
        "Programming Language :: Python",
    ]
    assert metadata.urls == {
        "changelog": "github.com/some/repo/blob/master/CHANGELOG.rst",
        "documentation": "readthedocs.org",
        "homepage": "example.com",
        "repository": "github.com/some/repo",
    }
    assert metadata.entrypoints == {
        "custom": {
            "full-metadata": "full_metadata:main_custom",
        },
    }
    assert metadata.scripts == {
        "full-metadata": "full_metadata:main_cli",
    }
    assert metadata.gui_scripts == {
        "full-metadata-gui": "full_metadata:main_gui",
    }
    assert list(map(str, metadata.dependencies)) == [
        "dependency1",
        "dependency2>1.0.0",
        "dependency3[extra]",
        'dependency4; os_name != "nt"',
        'dependency5[other-extra]>1.0; os_name == "nt"',
    ]
    assert list(metadata.optional_dependencies.keys()) == ["test"]
    assert list(map(str, metadata.optional_dependencies["test"])) == [
        "test_dependency",
        "test_dependency[test_extra]",
        'test_dependency[test_extra2]>3.0; os_name == "nt"',
    ]


def test_read_license(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata2")
    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))

    assert isinstance(metadata.license, pyproject_metadata.License)
    assert metadata.license.file == pathlib.Path("LICENSE")
    assert metadata.license.text == "Some license! 👋\n"


@pytest.mark.parametrize(
    ("package", "content_type"),
    [
        ("full-metadata", "text/markdown"),
        ("full-metadata2", "text/x-rst"),
    ],
)
def test_readme_content_type(
    package: str, content_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "packages" / package)
    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))

    assert isinstance(metadata.readme, pyproject_metadata.Readme)
    assert metadata.readme.content_type == content_type


def test_readme_content_type_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/unknown-readme-type")
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match=re.escape(
            "Could not infer content type for readme file 'README.just-made-this-up-now'"
        ),
    ), open("pyproject.toml", "rb") as f:
        pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))


def test_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_json()

    assert core_metadata == {
        "author": "Example!",
        "author_email": "Unknown <example@example.com>",
        "classifier": [
            "Development Status :: 4 - Beta",
            "Programming Language :: Python",
        ],
        "description": "some readme 👋\n",
        "description_content_type": "text/markdown",
        "keywords": ["trampolim", "is", "interesting"],
        "license": "some license text",
        "maintainer_email": "Other Example <other@example.com>",
        "metadata_version": "2.1",
        "name": "full_metadata",
        "project_url": [
            "homepage, example.com",
            "documentation, readthedocs.org",
            "repository, github.com/some/repo",
            "changelog, github.com/some/repo/blob/master/CHANGELOG.rst",
        ],
        "provides_extra": ["test"],
        "requires_dist": [
            "dependency1",
            "dependency2>1.0.0",
            "dependency3[extra]",
            'dependency4; os_name != "nt"',
            'dependency5[other-extra]>1.0; os_name == "nt"',
            'test_dependency; extra == "test"',
            'test_dependency[test_extra]; extra == "test"',
            'test_dependency[test_extra2]>3.0; os_name == "nt" and extra == "test"',
        ],
        "requires_python": ">=3.8",
        "summary": "A package with all the metadata :)",
        "version": "3.2.1",
    }


def test_as_rfc822(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/full-metadata")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_rfc822()
    assert core_metadata.items() == [
        ("Metadata-Version", "2.1"),
        ("Name", "full_metadata"),
        ("Version", "3.2.1"),
        ("Summary", "A package with all the metadata :)"),
        ("Keywords", "trampolim,is,interesting"),
        ("Author", "Example!"),
        ("Author-Email", "Unknown <example@example.com>"),
        ("Maintainer-Email", "Other Example <other@example.com>"),
        ("License", "some license text"),
        ("Classifier", "Development Status :: 4 - Beta"),
        ("Classifier", "Programming Language :: Python"),
        ("Project-URL", "homepage, example.com"),
        ("Project-URL", "documentation, readthedocs.org"),
        ("Project-URL", "repository, github.com/some/repo"),
        ("Project-URL", "changelog, github.com/some/repo/blob/master/CHANGELOG.rst"),
        ("Requires-Python", ">=3.8"),
        ("Requires-Dist", "dependency1"),
        ("Requires-Dist", "dependency2>1.0.0"),
        ("Requires-Dist", "dependency3[extra]"),
        ("Requires-Dist", 'dependency4; os_name != "nt"'),
        ("Requires-Dist", 'dependency5[other-extra]>1.0; os_name == "nt"'),
        ("Provides-Extra", "test"),
        ("Requires-Dist", 'test_dependency; extra == "test"'),
        ("Requires-Dist", 'test_dependency[test_extra]; extra == "test"'),
        (
            "Requires-Dist",
            'test_dependency[test_extra2]>3.0; os_name == "nt" and extra == "test"',
        ),
        ("Description-Content-Type", "text/markdown"),
    ]
    assert core_metadata.get_payload() == "some readme 👋\n"


def test_as_json_default_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/default_extra")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_json()
    assert core_metadata == {
        "metadata_version": "2.6",
        "name": "default_extras",
        "version": "0.1.2",
        "default_extra": ["backend1", "backend2", "backend3"],
        "provides_extra": ["backend1", "backend2", "backend3", "backend4"],
        "requires_dist": [
            'a; extra == "backend1"',
            'b; extra == "backend2"',
            'c; extra == "backend3"',
            'd; extra == "backend4"',
        ],
    }


def test_as_rfc822_default_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/default_extra")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_rfc822()
    assert core_metadata.items() == [
        ("Metadata-Version", "2.6"),
        ("Name", "default_extras"),
        ("Version", "0.1.2"),
        ("Provides-Extra", "backend1"),
        ("Requires-Dist", 'a; extra == "backend1"'),
        ("Provides-Extra", "backend2"),
        ("Requires-Dist", 'b; extra == "backend2"'),
        ("Provides-Extra", "backend3"),
        ("Requires-Dist", 'c; extra == "backend3"'),
        ("Provides-Extra", "backend4"),
        ("Requires-Dist", 'd; extra == "backend4"'),
        ("Default-Extra", "backend1"),
        ("Default-Extra", "backend2"),
        ("Default-Extra", "backend3"),
    ]

    assert core_metadata.get_payload() is None


def test_as_json_spdx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/spdx")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_json()
    assert core_metadata == {
        "license_expression": "MIT OR GPL-2.0-or-later OR (FSFUL AND BSD-2-Clause)",
        "license_file": [
            "AUTHORS.txt",
            "LICENSE.md",
            "LICENSE.txt",
            "licenses/LICENSE.MIT",
        ],
        "metadata_version": "2.4",
        "name": "example",
        "version": "1.2.3",
    }


def test_as_rfc822_spdx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/spdx")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    core_metadata = metadata.as_rfc822()
    assert core_metadata.items() == [
        ("Metadata-Version", "2.4"),
        ("Name", "example"),
        ("Version", "1.2.3"),
        ("License-Expression", "MIT OR GPL-2.0-or-later OR (FSFUL AND BSD-2-Clause)"),
        ("License-File", "AUTHORS.txt"),
        ("License-File", "LICENSE.md"),
        ("License-File", "LICENSE.txt"),
        ("License-File", "licenses/LICENSE.MIT"),
    ]

    assert core_metadata.get_payload() is None


def test_as_rfc822_spdx_empty_glob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, all_errors: bool
) -> None:
    shutil.copytree(DIR / "packages/spdx", tmp_path / "spdx")
    monkeypatch.chdir(tmp_path / "spdx")

    pathlib.Path("AUTHORS.txt").unlink()
    msg = "Every pattern in \"project.license-files\" must match at least one file: 'AUTHORS*' did not match any"

    with open("pyproject.toml", "rb") as f:
        if all_errors:
            with pytest.raises(
                pyproject_metadata.errors.ExceptionGroup,
            ) as execinfo:
                pyproject_metadata.StandardMetadata.from_pyproject(
                    tomllib.load(f), all_errors=all_errors
                )
            assert "Failed to parse pyproject.toml" in str(execinfo.value)
            assert [msg] == [str(e) for e in execinfo.value.exceptions]
        else:
            with pytest.raises(
                pyproject_metadata.ConfigurationError,
                match=re.escape(msg),
            ):
                pyproject_metadata.StandardMetadata.from_pyproject(
                    tomllib.load(f), all_errors=all_errors
                )


def test_license_file_24(
    metadata_version: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(DIR / "packages/fulltext_license")
    pre_spdx = (
        metadata_version in pyproject_metadata.constants.PRE_SPDX_METADATA_VERSIONS
    )
    with (
        contextlib.nullcontext()
        if pre_spdx
        else pytest.warns(pyproject_metadata.errors.ConfigurationWarning)
    ):
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "fulltext_license",
                    "version": "0.1.0",
                    "license": {"file": "LICENSE.txt"},
                },
            },
            metadata_version=metadata_version,
        )
    message = str(metadata.as_rfc822())
    if metadata_version in pyproject_metadata.constants.PRE_SPDX_METADATA_VERSIONS:
        assert "License-File: LICENSE.txt" not in message
    else:
        assert "License-File: LICENSE.txt" in message


def test_as_rfc822_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(DIR / "packages/dynamic-description")

    with open("pyproject.toml", "rb") as f:
        metadata = pyproject_metadata.StandardMetadata.from_pyproject(tomllib.load(f))
    metadata.dynamic_metadata = ["description"]
    core_metadata = metadata.as_rfc822()
    assert core_metadata.items() == [
        ("Metadata-Version", "2.2"),
        ("Name", "dynamic-description"),
        ("Version", "1.0.0"),
        ("Dynamic", "description"),
    ]


def test_as_rfc822_set_metadata(metadata_version: str) -> None:
    metadata = pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "hi",
                "version": "1.2",
                "optional-dependencies": {
                    "under_score": ["some_package"],
                    "da-sh": ["some-package"],
                    "do.t": ["some.package"],
                    "empty": [],
                },
            }
        },
        metadata_version=metadata_version,
    )
    assert metadata.metadata_version == metadata_version

    rfc822 = bytes(metadata.as_rfc822()).decode("utf-8")

    assert f"Metadata-Version: {metadata_version}" in rfc822

    assert "Provides-Extra: under-score" in rfc822
    assert "Provides-Extra: da-sh" in rfc822
    assert "Provides-Extra: do-t" in rfc822
    assert "Provides-Extra: empty" in rfc822
    assert 'Requires-Dist: some_package; extra == "under-score"' in rfc822
    assert 'Requires-Dist: some-package; extra == "da-sh"' in rfc822
    assert 'Requires-Dist: some.package; extra == "do-t"' in rfc822


def test_as_json_set_metadata() -> None:
    metadata = pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "hi",
                "version": "1.2",
                "optional-dependencies": {
                    "under_score": ["some_package"],
                    "da-sh": ["some-package"],
                    "do.t": ["some.package"],
                    "empty": [],
                },
            }
        },
        metadata_version="2.1",
    )
    assert metadata.metadata_version == "2.1"

    json = metadata.as_json()

    assert json == {
        "metadata_version": "2.1",
        "name": "hi",
        "provides_extra": ["under-score", "da-sh", "do-t", "empty"],
        "requires_dist": [
            'some_package; extra == "under-score"',
            'some-package; extra == "da-sh"',
            'some.package; extra == "do-t"',
        ],
        "version": "1.2",
    }


def test_as_rfc822_set_metadata_invalid() -> None:
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match="The metadata_version must be one of",
    ) as err:
        pyproject_metadata.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "hi",
                    "version": "1.2",
                },
            },
            metadata_version="2.0",
        )
    assert "2.1" in str(err.value)
    assert "2.2" in str(err.value)
    assert "2.3" in str(err.value)


def test_as_rfc822_invalid_dynamic() -> None:
    metadata = pyproject_metadata.StandardMetadata(
        name="something",
        version=packaging.version.Version("1.0.0"),
        dynamic_metadata=["name"],
    )
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match="Metadata field 'name' cannot be declared dynamic",
    ):
        metadata.as_rfc822()
    metadata.dynamic_metadata = ["Version"]
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match="Metadata field 'Version' cannot be declared dynamic",
    ):
        metadata.as_rfc822()
    metadata.dynamic_metadata = ["unknown"]
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match="Unknown metadata field 'unknown' cannot be declared dynamic",
    ):
        metadata.as_rfc822()


def test_as_rfc822_mapped_dynamic() -> None:
    metadata = pyproject_metadata.StandardMetadata(
        name="something",
        version=packaging.version.Version("1.0.0"),
        dynamic_metadata=list(pyproject_metadata.field_to_metadata("description")),
    )
    assert (
        str(metadata.as_rfc822())
        == "Metadata-Version: 2.2\nName: something\nVersion: 1.0.0\nDynamic: Summary\n\n"
    )


def test_as_rfc822_missing_version() -> None:
    metadata = pyproject_metadata.StandardMetadata(name="something")
    with pytest.raises(
        pyproject_metadata.ConfigurationError, match='Field "project.version" missing'
    ):
        metadata.as_rfc822()


def test_statically_defined_dynamic_field() -> None:
    with pytest.raises(
        pyproject_metadata.ConfigurationError,
        match='Field "project.version" declared as dynamic in "project.dynamic" but is defined',
    ):
        pyproject_metadata.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "example",
                    "version": "1.2.3",
                    "dynamic": [
                        "version",
                    ],
                },
            }
        )


@pytest.mark.parametrize(
    "value",
    [
        "<3.10",
        ">3.8,<3.11",
        ">3.8,<3.11,!=3.8.4",
        "~=3.10,!=3.10.3",
    ],
)
def test_requires_python(value: str) -> None:
    pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "0.1.0",
                "requires-python": value,
            },
        }
    )


def test_version_dynamic() -> None:
    metadata = pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "dynamic": [
                    "version",
                ],
            },
        }
    )
    metadata.version = packaging.version.Version("1.2.3")


def test_modify_dynamic() -> None:
    metadata = pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {
                "name": "example",
                "version": "1.2.3",
                "dynamic": [
                    "requires-python",
                ],
            },
        }
    )
    metadata.requires_python = packaging.specifiers.SpecifierSet(">=3.12")
    metadata.version = packaging.version.Version("1.2.3")


def test_missing_keys_warns() -> None:
    with pytest.warns(
        pyproject_metadata.errors.ConfigurationWarning,
        match=re.escape("Extra keys present in \"project\": 'not-real-key'"),
    ):
        pyproject_metadata.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "example",
                    "version": "1.2.3",
                    "not-real-key": True,
                },
            }
        )


def test_missing_keys_okay() -> None:
    pyproject_metadata.StandardMetadata.from_pyproject(
        {
            "project": {"name": "example", "version": "1.2.3", "not-real-key": True},
        },
        allow_extra_keys=True,
    )


def test_extra_top_level() -> None:
    assert not pyproject_metadata.extras_top_level(
        {"project": {}, "dependency-groups": {}}
    )
    assert {"also-not-real", "not-real"} == pyproject_metadata.extras_top_level(
        {
            "not-real": {},
            "also-not-real": {},
            "project": {},
            "build-system": {},
        }
    )


def test_extra_build_system() -> None:
    assert not pyproject_metadata.extras_build_system(
        {
            "build-system": {
                "build-backend": "one",
                "requires": ["two"],
                "backend-path": "local",
            },
        }
    )
    assert {"also-not-real", "not-real"} == pyproject_metadata.extras_build_system(
        {
            "build-system": {
                "not-real": {},
                "also-not-real": {},
            }
        }
    )


def test_multiline_description_warns() -> None:
    with pytest.warns(
        pyproject_metadata.errors.ConfigurationWarning,
        match=re.escape(
            'The one-line summary "project.description" should not contain more than one line. Readers might merge or truncate newlines.'
        ),
    ):
        pyproject_metadata.StandardMetadata.from_pyproject(
            {
                "project": {
                    "name": "example",
                    "version": "1.2.3",
                    "description": "this\nis multiline",
                },
            }
        )
