# Testing Guidelines for banyan-extract

## Overview
This document provides comprehensive guidelines for writing tests in the banyan-extract codebase. Tests should serve dual purposes: functional verification and user education.

## Table of Contents
1. [Test Structure](#test-structure)
2. [Test Types](#test-types)
3. [Test Organization](#test-organization)
4. [Writing Effective Tests](#writing-effective-tests)
5. [Mocking and Fixtures](#mocking-and-fixtures)
6. [Example-Based Testing](#example-based-testing)
7. [Test Coverage](#test-coverage)
8. [Test Maintenance](#test-maintenance)

## Test Structure

### Basic Test Structure
```python
def test_function_name():
    """
    Clear description of what this test verifies.
    
    This docstring should explain:
    - What functionality is being tested
    - What the expected behavior is
    - Any important setup or assumptions
    """
    # Setup (Arrange)
    # Execute (Act)
    # Verify (Assert)
    # Cleanup (if needed)
```

### Test Naming Conventions
- Use `test_` prefix for all test functions
- Use descriptive names: `test_process_pdf_with_nemoparse`
- Avoid generic names like `test_function1`
- Use underscores for readability

## Test Types

### Unit Tests
- Test individual functions or methods in isolation
- Focus on single responsibility
- Use mocking for dependencies
- Fast execution

### Integration Tests
- Test interactions between components
- Verify workflows work end-to-end
- May use real dependencies
- Slower execution

### Example Tests
- Demonstrate real-world usage
- Serve as user documentation
- Show best practices
- Can be used as templates

## Test Organization

### Directory Structure
```
tests/
├── conftest.py          # Shared fixtures
├── utils.py             # Test utilities
├── data/                # Test data files
│   ├── processors/      # Processor test data
│   ├── outputs/         # Output test data
│   └── converters/      # Converter test data
├── examples/            # Example-based tests
│   ├── basic/           # Basic usage examples
│   ├── advanced/        # Advanced usage examples
│   └── integration/     # Integration examples
├── unit/                # Unit tests
│   ├── test_processors/ # Processor unit tests
│   ├── test_outputs/    # Output unit tests
│   └── test_converters/ # Converter unit tests
└── integration/         # Integration tests
```

### Test File Naming
- `test_<module>_<function>.py` for unit tests
- `test_<workflow>.py` for integration tests
- `example_<use_case>.py` for example tests

## Writing Effective Tests

### Test Characteristics
1. **Clear**: Easy to understand purpose
2. **Isolated**: Independent of other tests
3. **Repeatable**: Same result every time
4. **Fast**: Quick execution
5. **Comprehensive**: Cover edge cases

### Test Pattern: Arrange-Act-Assert
```python
def test_pdf_processing():
    # Arrange
    processor = NemoparseProcessor(endpoint="mock_endpoint")
    test_file = "tests/data/sample.pdf"
    
    # Act
    result = processor.process_document(test_file)
    
    # Assert
    assert result is not None
    assert len(result.pages) > 0
    assert isinstance(result.pages[0], dict)
```

### Best Practices
- **One assertion per logical concept**
- **Use descriptive assertion messages**
- **Test both happy paths and edge cases**
- **Keep tests focused on single functionality**
- **Use setup/teardown appropriately**
- **Prefer real implementations over mocks**
- **Test behavior, not implementation details**

## Mocking Philosophy and Guidelines

### Core Principles
1. **Prefer real implementations**: Use actual dependencies whenever possible
2. **Mocks are a last resort**: Only use when real dependencies are impractical
3. **Document and justify**: Every mock must have clear justification
4. **Behavior over implementation**: Test what code does, not how it's implemented
5. **Avoid hiding integration issues**: Mocks should not mask real-world problems

### When Mocking is Appropriate
Mocks should **only** be used when:
- External API calls that require network access
- Services with usage limits or costs
- Hardware dependencies
- Time-sensitive operations
- Operations that modify system state
- Truly impractical to test with real implementations

### When to Avoid Mocking
Do **not** mock when:
- Testing internal component interactions
- Real dependencies are available and fast enough
- Testing simple file operations
- Testing database operations (use test databases instead)
- The mock would be more complex than the real implementation

### Mocking Best Practices

#### 1. Justify Every Mock
```python
from unittest.mock import patch, MagicMock

def test_nemoparse_with_mock():
    """
    Test NemoparseProcessor with mocked API.
    
    Mocking justified because:
    - Requires external network API
    - API has rate limits
    - Testing specific error handling
    """
    with patch('requests.post') as mock_post:
        # Mock setup with clear documentation
        mock_response = MagicMock()
        mock_response.json.return_value = {"pages": [{"elements": []}]}
        mock_post.return_value = mock_response
        
        processor = NemoparseProcessor(endpoint="http://mock")
        result = processor.process_document("test.pdf")
        
        # Verify mock was called appropriately
        assert mock_post.called
        assert result is not None
```

#### 2. Keep Mocks Simple
```python
# Good: Simple mock that focuses on behavior
def test_error_handling():
    """
    Test error handling when API fails.
    
    Mocking justified: Testing specific error conditions
    that are hard to reproduce with real API.
    """
    with patch('requests.post') as mock_post:
        mock_post.side_effect = ConnectionError("API unavailable")
        
        processor = NemoparseProcessor()
        result = processor.process_document("test.pdf")
        
        assert result is None
        # Verify appropriate error handling occurred
```

#### 3. Prefer Real Implementations
```python
# Better: Use real implementation when possible
def test_local_file_processing():
    """
    Test file processing with real file system operations.
    
    No mocking needed - using real files is practical
    and provides better test coverage.
    """
    # Use real file operations
    test_file = "tests/data/sample.pdf"
    processor = LocalProcessor()
    
    result = processor.process_document(test_file)
    
    assert result is not None
    assert len(result.pages) > 0
```

### Mocking Anti-Patterns to Avoid

#### ❌ Over-mocking
```python
# Bad: Mocking everything hides real issues
def test_over_mocked():
    with patch('os.path.exists') as mock_exists, \
         patch('builtins.open') as mock_open, \
         patch('json.load') as mock_json:  # Too much mocking!
        # This test doesn't verify real behavior
        pass
```

#### ❌ Testing Implementation Details
```python
# Bad: Testing how something is implemented
def test_implementation_detail():
    with patch.object(Processor, '_internal_method') as mock_internal:
        # This tests internal implementation, not behavior
        processor.process_document("test.pdf")
        assert mock_internal.called  # Tests implementation, not behavior
```

#### ❌ Complex Mock Setups
```python
# Bad: Mock setup more complex than real code
def test_complex_mock():
    with patch('complex_module.ComplexClass') as mock_complex:
        mock_instance = mock_complex.return_value
        mock_instance.method1.return_value = "value1"
        mock_instance.method2.side_effect = ["a", "b", "c"]
        mock_instance.property1 = "prop1"
        mock_instance.property2 = MagicMock()
        # ... 20 more lines of mock setup
        # This is a sign mocks are being overused
```

### Fixtures
Use pytest fixtures for reusable test setup:

```python
# In conftest.py
@pytest.fixture
def sample_processor():
    return NemoparseProcessor(endpoint="mock_endpoint", sort_by_position=True)

# In test file
def test_processor_initialization(sample_processor):
    assert sample_processor.sort_by_position is True
```

## Example-Based Testing

### Characteristics of Good Examples
- **Realistic**: Use actual file formats and data
- **Complete**: Show full workflows
- **Documented**: Explain what the example demonstrates
- **Reusable**: Can be adapted for real use
- **Educational**: Teach best practices

### Example Test Structure
```python
def test_example_basic_pdf_processing():
    """
    Example: Basic PDF processing with Nemoparse backend
    
    This example demonstrates:
    - How to initialize a NemoparseProcessor
    - How to process a single PDF document
    - How to save the output
    - Basic configuration options
    
    Users can adapt this example by:
    - Changing the endpoint URL
    - Adding different configuration options
    - Processing different file types
    """
    # Initialize processor with mock endpoint
    processor = NemoparseProcessor(
        endpoint_url="http://example.com/nemoparse",
        model_name="nvidia/nemoretriever-parse",
        sort_by_position=True
    )
    
    # Process a sample document
    test_file = "tests/data/examples/sample.pdf"
    output = processor.process_document(test_file)
    
    # Save the output
    output_dir = "tests/data/examples/output"
    output.save_output(output_dir, "sample_output")
    
    # Verify the output
    assert output is not None
    assert len(output.pages) > 0
    
    # Clean up (in real usage, you might want to keep the output)
    import shutil
    shutil.rmtree(output_dir, ignore_errors=True)
```

### Example Organization
```
tests/examples/
├── basic/                    # Basic usage examples
│   ├── test_pdf_processing.py
│   ├── test_pptx_processing.py
│   └── test_batch_processing.py
├── advanced/                 # Advanced usage examples
│   ├── test_custom_config.py
│   ├── test_ocr_integration.py
│   └── test_error_handling.py
└── integration/              # Integration examples
    ├── test_full_workflow.py
    ├── test_multi_backend.py
    └── test_large_documents.py
```

## Test Coverage

### Coverage Goals
- **Core modules**: 90%+ coverage
- **Utilities**: 80%+ coverage  
- **Integration**: 70%+ coverage
- **Examples**: Focus on key use cases

### Coverage Exclusions
- Generated code
- External library code
- Configuration files
- Some error handling paths

### Running Coverage
```bash
# Run tests with coverage
python -m pytest --cov=src/banyan_extract --cov-report=html tests/

# Check coverage report
open htmlcov/index.html
```

## Test Maintenance

### Updating Tests
- Update tests when functionality changes
- Add new tests for new features
- Review and update examples regularly
- Keep mocks in sync with real APIs

### Test Review Process
1. **Code changes**: Update relevant tests
2. **New features**: Add comprehensive tests with real implementations
3. **Bug fixes**: Add regression tests (preferably without mocks)
4. **API changes**: Update mocks and examples, but prefer real implementations

### Test Quality Checklist
- [ ] Tests are clear and well-documented
- [ ] Tests cover main functionality and edge cases
- [ ] Tests use appropriate mocking (sparingly and justified)
- [ ] Tests follow naming conventions
- [ ] Tests are properly organized
- [ ] Examples are realistic and educational
- [ ] Tests use real implementations where practical
- [ ] Tests pass consistently
- [ ] Mocks don't hide integration issues

## Contributing Tests

### For New Contributors
1. **Start small**: Begin with simple unit tests
2. **Follow patterns**: Use existing tests as templates
3. **Ask questions**: If unsure about testing approach
4. **Review guidelines**: Follow these testing guidelines
5. **Test your tests**: Ensure they work reliably

### Test Contribution Checklist
- [ ] Tests follow the established patterns
- [ ] Tests are properly documented
- [ ] Tests cover the intended functionality
- [ ] Tests are placed in the correct location
- [ ] Tests pass on your local machine
- [ ] Tests don't break existing functionality
- [ ] Mock usage is minimal and justified
- [ ] Tests focus on behavior, not implementation

## Resources
- [pytest documentation](https://docs.pytest.org/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Python testing best practices](https://realpython.com/python-testing/)

## Getting Help
- Check existing tests for patterns
- Review the example-based tests
- Ask in project discussions
- Consult the testing guidelines
- Look at pytest documentation