.PHONY: bootstrap-python doc-lint oss-evidence-inventory oss-release-scan test-scripts typecheck verify verify-full

bootstrap-python:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec "$$PYBIN" -m pip install -r requirements-dev.lock'

doc-lint:
	PYBIN="$(PYBIN)" bash ./scripts/run_doc_lint.sh

oss-release-scan:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -B scripts/oss_release_scan.py --scope public-copy --format text --fail-on blocker'

oss-evidence-inventory:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; mkdir -p .tmp/oss_release; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -B scripts/oss_evidence_prepare.py inventory --out .tmp/oss_release/evidence_candidates.tsv'

test-scripts:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -m unittest discover -s scripts -p "test_*.py" -v'

typecheck:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -m mypy --config-file pyproject.toml'

verify:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -B scripts/verify_suite.py --format plain'

verify-full:
	@bash -c 'source ./scripts/_pybin.sh; planveyor_pybin_resolve "$$PWD"; planveyor_pybin_validate_version "$$PYBIN"; exec env PYTHONDONTWRITEBYTECODE=1 "$$PYBIN" -B scripts/verify_suite.py --format plain --full'
