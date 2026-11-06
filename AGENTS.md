# AGENTS.md - Guidelines for Agentic Coding in banyan-extract

This document provides guidelines for AI agents working on the banyan-extract codebase.

## Style and Conventions

**No Emojis**: No emojis anywhere in the codebase. If you find one, remove it.

**File Naming**: Use descriptive names (e.g., `chat_service.py`, `mcp_tool_manager.py`), not generic ones (`utils.py`, `helpers.py`). Exception: top-level entry points like `atlas/main.py`.

**File Size**: Prefer 400 lines or fewer.

**Documentation**: PRs must update relevant docs in `/docs` (architecture, features, API, config, troubleshooting).

**Changelog**: Add a 1-2 line entry to `CHANGELOG.md` for every PR. Format: `### PR #<number> - YYYY-MM-DD`.

**Date Stamps**: Include `YYYY-MM-DD` dates in doc filenames or section headers to track staleness.

## Agent-Specific Guidelines

### .env File Handling (ALL AGENTS)

**STRICT RULES FOR ALL AGENTS:**
1. Agents may READ .env files but NEVER MODIFY or DELETE them
2. This applies to all agents without exception
3. Any testing that requires .env configuration should use temporary files or ask for user permission

### Feature-Implementer Agent

**Strict Guidelines:**
1. **NEVER modify or delete .env files - read only**: Agents may read .env files but never modify or delete them
2. **No Special Characters**: Never use unicode, special symbols, emojis, or non-standard characters in code or output
3. **Simplicity First**: Prefer simpler implementations over complex logic
4. **Minimal Dependency Checking**: Avoid excessive dependency checking unless explicitly required
5. **Focused Testing**: Write comprehensive but focused tests targeting key functionality
6. **Proportional Testing**: Avoid excessive tests for small features (e.g., 100+ tests for a couple lines of code)
7. **Relative Paths Only**: Never use absolute paths for sample files in tests
8. **Code Quality**: Prioritize clean, maintainable, and well-documented code
9. **Scope Adherence**: Implement only the exact feature requested, no extra functionality

### Code-Review Agent

**Strict Guidelines:**
1. **NEVER modify or delete .env files - read only**: Agents may read .env files but never modify or delete them
2. **No Special Characters**: Ensure no unicode, special symbols, emojis, or non-standard characters in code
3. **Simplicity Review**: Favor simpler solutions and flag overly complex implementations
4. **Test Quality**: Verify tests are comprehensive but not excessive for the feature size
5. **Path Validation**: Ensure no absolute paths are used in test files
6. **Scope Validation**: Confirm implementation matches exact requirements, no scope creep

### Planning Agent

**Strict Guidelines:**
1. **NEVER modify or delete .env files - read only**: Agents may read .env files but never modify or delete them
2. **No Special Characters**: Avoid unicode, special symbols, emojis in planning documents
3. **Simplicity First**: Plan for the simplest viable implementation first - always prefer simpler solutions over complex architectures
4. **Avoid Overly Complex Architectures**: Only propose complex solutions when absolutely necessary and provide clear justification
5. **Proportional Testing**: Plan test coverage that matches feature complexity - avoid excessive testing for simple features
6. **Relative Paths Only**: Never use absolute paths for sample files in test plans - always use relative paths from project root
7. **Minimal Dependencies**: Avoid adding unnecessary dependencies in plans
8. **Clear Scope**: Define exact feature boundaries to prevent scope creep
9. **Justify Complexity**: Any complex solution must include clear justification explaining why simpler approaches won't work

**Test Planning Guidelines:**
- **Simple Features (1-2 functions)**: 3-5 focused tests covering main functionality and edge cases
- **Medium Features (3-5 functions)**: 5-10 tests covering main paths, edge cases, and error handling
- **Complex Features (6+ functions)**: 10-20 tests covering comprehensive scenarios, but avoid excessive testing
- **Avoid**: Planning 100+ tests for simple features or testing every minor implementation detail

**Path Usage Guidelines:**
- **Test Data Location**: All test data should be referenced using relative paths from project root
- **Test Data Organization**: Plan for test data to be organized in `tests/data/` directory structure
- **No Absolute Paths**: Never use absolute paths like `/home/user/project/tests/data/` - always use `tests/data/`
- **Cross-Platform Compatibility**: Ensure paths work on all platforms (Windows, Linux, macOS)

**Implementation Complexity Guidelines:**
- **Simple Implementation**: Single function/method, straightforward logic, minimal dependencies
- **Medium Implementation**: Multiple related functions, some conditional logic, moderate dependencies
- **Complex Implementation**: Multiple components, complex workflows, significant dependencies - requires detailed justification

**Alignment with Other Agents:**
- Planning agent guidelines should align with Feature-Implementer agent's simplicity focus
- Planning agent guidelines should align with Code-Review agent's proportional testing approach
- All agents should enforce relative path usage consistently

## Claude Code Agents

**test-report-runner**: Run frequently after code changes to verify tests pass.

**final-checklist-reviewer**: Run once at the end of a PR to validate requirements, standards, and quality gates.

## Build/Lint/Test Commands

### Testing

**Run all tests:**
```bash
python3 -m pytest tests/
```

**Run a single test file:**
```bash
python3 -m pytest tests/path/to/test_file.py
```

**Run a specific test:**
```bash
python3 -m pytest tests/path/to/test_file.py::test_name
```

**Run tests with coverage:**
```bash
python3 -m pytest --cov=src/banyan_extract tests/
```

**Run tests with verbose output:**
```bash
python3 -m pytest -v tests/
```

### Linting and Formatting

**Run ruff linter (if available):**
```bash
python3 -m ruff check src/
```

**Run ruff formatter (if available):**
```bash
python3 -m ruff format src/
```

**Run flake8 (if available):**
```bash
python3 -m flake8 src/
```

### Building

**Build the package:**
```bash
python3 -m pip install .
```

**Build with optional dependencies:**
```bash
python3 -m pip install .[marker]
python3 -m pip install .[nemotronparse]
```

**Install in development mode:**
```bash
python3 -m pip install -e .
```

## Code Style Guidelines

### Imports

1. **Group imports** in the following order:
   - Standard library imports
   - Third-party library imports
   - Local application imports

2. **Use absolute imports** for local modules:
   ```python
   from banyan_extract.processor import Processor
   ```

3. **Avoid wildcard imports** (except in `__init__.py`):
   ```python
   # Good
   from module import specific_function
   
   # Avoid
   from module import *
   ```

### Formatting

1. **Line length**: Maximum 120 characters
2. **Indentation**: 4 spaces (no tabs)
3. **Spacing**:
   - Two blank lines around top-level functions and classes
   - One blank line around method definitions
   - No spaces inside parentheses, brackets, or braces
4. **Quotes**: Use double quotes for strings unless single quotes are needed
5. **Docstrings**: Use Google-style docstrings for public functions and classes

### Types

1. **Use type hints** for all function parameters and return values
2. **Use PEP 604 union syntax** (X | Y) instead of Union[X, Y]
3. **Use Optional[X]** for nullable types instead of Union[X, None]
4. **Use Annotated** for complex types with metadata

### Naming Conventions

1. **Variables and functions**: snake_case
   ```python
   def process_document(self, filepath):
       file_pages = []
   ```

2. **Classes**: PascalCase
   ```python
   class NemoparseProcessor:
   ```

3. **Constants**: UPPER_SNAKE_CASE
   ```python
   MAX_RETRIES = 3
   ```

4. **Private members**: Leading underscore
   ```python
   def _encode_image(self, image):
   ```

5. **Boolean variables**: Prefix with `is_`, `has_`, or `can_`
   ```python
   is_valid = True
   has_error = False
   ```

### Error Handling

1. **Use specific exceptions** instead of generic Exception
2. **Provide meaningful error messages**
3. **Use try-except blocks** for operations that might fail
4. **Clean up resources** in finally blocks when needed

```python
try:
    base64_encoded_data = base64.b64encode(image)
    base64_string = base64_encoded_data.decode("utf-8")
    return base64_string
except Exception as e:
    print(f"An error occurred trying to encode the document: {e}")
    return None
```

### Documentation

1. **Use Google-style docstrings** for public functions and classes:
   ```python
   def sort_elements_by_position(self, bbox_data, width, height):
       """
       Sort document elements based on their spatial position.
       
       Args:
           bbox_data: List of element dictionaries from API response
           width: Page width in pixels
           height: Page height in pixels
           
       Returns:
           List of sorted element dictionaries
       """
   ```

2. **Document complex logic** with inline comments:
   ```python
   # Convert normalized coordinates to absolute pixels
   # Use top-left corner (ymin, xmin) instead of center for better reading order
   y_top = bbox['ymin'] * height
   x_left = bbox['xmin'] * width
   ```

### Testing

1. **Write unit tests** for all new functionality
2. **Follow the test structure** outlined in Test-plan.md
3. **Use pytest** as the test runner
4. **Mock external dependencies** in unit tests
5. **Test both success and failure cases**

## Project Structure

```
banyan-extract/
├── src/
│   └── banyan_extract/
│       ├── __init__.py
│       ├── cli.py
│       ├── converter/
│       ├── output/
│       └── processor/
├── tests/
├── examples/
└── docs/
```

## Common Patterns

### Processor Pattern

All processors should inherit from the base `Processor` class:

```python
from .processor import Processor

class NemoparseProcessor(Processor):
    def __init__(self, endpoint_url="", model_name="nvidia/nemoretriever-parse"):
        super().__init__()
        # Initialize processor-specific attributes
```

### Output Pattern

Each processor should have a corresponding output class:

```python
class NemoparseOutput:
    def __init__(self):
        self.pages = []
    
    def add_output(self, page_data):
        self.pages.append(page_data)
    
    def save_output(self, output_dir, basename):
        # Save output files
```

### CLI Integration

New features should be exposed through the CLI when appropriate:

```python
parser.add_argument("--sort_by_position", action="store_true", default=True, 
                   help="Sort elements by spatial position for logical reading order")
```

## Environment Variables

The project uses environment variables for configuration:

```
NEMOPARSE_ENDPOINT=your_endpoint_url
NEMOPARSE_MODEL=your_model_name
```

## Dependencies

### Required Dependencies
- python-pptx
- pandas
- pdf2image
- python-dotenv

### Optional Dependencies
- marker-pdf (for marker backend)
- surya-ocr (for marker backend)
- openai (for nemotronparse backend)

## Best Practices

1. **Keep functions small** and focused on a single responsibility
2. **Use descriptive names** for variables and functions
3. **Handle edge cases** gracefully
4. **Write tests first** when possible (TDD)
5. **Follow the existing code patterns** in the codebase
6. **Document assumptions** and limitations
7. **Keep the code DRY** (Don't Repeat Yourself)
8. **Write maintainable code** that others can understand

## Version Control

1. **Use feature branches** for new development
2. **Write meaningful commit messages**
3. **Keep commits small** and focused
4. **Update documentation** when making changes
5. **Run tests before committing**

## Continuous Integration

The project uses GitHub Actions for CI/CD. Make sure:
1. All tests pass before pushing
2. Code follows the style guidelines
3. Documentation is updated
4. New features have corresponding tests
