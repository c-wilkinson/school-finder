## Summary

<!-- Briefly describe what this pull request changes and why. -->

## Related issue

<!-- Link the issue this PR addresses, if applicable. Use "Closes #123" to automatically close it when merged. -->

Closes #

## Changes

<!-- Summarise the main changes made. -->

-

## Testing

<!-- Explain how the changes were verified. Include relevant test results or manual testing steps. -->

- [ ] Tests pass locally (`python -m pytest`)
- [ ] New or updated tests cover the changed behaviour
- [ ] Overall coverage remains at or above 95%
- [ ] External HTTP calls are mocked in automated tests, where applicable

## Contributor checklist

<!-- Check the items that apply. Mark non-applicable items as N/A if useful. -->

- [ ] Changes follow the existing coding standards and architecture
- [ ] Business logic remains independent of CLI and Streamlit presentation layers
- [ ] Missing data is not silently treated as zero
- [ ] Derived values are distinguishable from official published values
- [ ] Data provenance and original identifiers are preserved where applicable
- [ ] Documentation has been updated for user-facing changes
- [ ] No credentials, temporary downloads or unnecessary generated datasets are committed
- [ ] Any new dependencies or third-party materials have been reviewed for necessity and licence compatibility

## Screenshots

<!-- For Streamlit UI changes, include before/after screenshots where useful. Otherwise, remove this section. -->

## Trade-offs and follow-up work

<!-- Describe any known limitations, design decisions, compatibility considerations or follow-up tasks. Remove if not applicable. -->

None.

---

Please ensure your contribution follows the [Contributing Guidelines](../CONTRIBUTING.md).