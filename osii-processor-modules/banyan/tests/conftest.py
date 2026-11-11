# Test Configuration and Fixtures
# This file contains pytest fixtures and configuration that are shared across all tests

import pytest
import os
from pathlib import Path

# Try to import dotenv for .env file loading
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    load_dotenv = None

# Base directory for test data
TEST_DATA_DIR = Path(__file__).parent / "data"


def load_environment_variables():
    """
    Load environment variables from .env file if available.
    
    This function attempts to load environment variables from a .env file
    using python-dotenv if available, or provides guidance if not available.
    
    Returns:
        dict: Dictionary of loaded environment variables
    """
    env_vars = {}
    
    # Try to load from .env file
    env_file = Path(__file__).parent.parent / ".env"
    
    if env_file.exists():
        if DOTENV_AVAILABLE and load_dotenv:
            # Use python-dotenv if available
            load_dotenv(env_file, override=True)
            env_vars = {
                'NEMOPARSE_ENDPOINT': os.environ.get('NEMOPARSE_ENDPOINT'),
                'NEMOPARSE_MODEL': os.environ.get('NEMOPARSE_MODEL')
            }
        else:
            # Fallback: manually read .env file
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip().strip('"').strip("'")
                            env_vars[key.strip()] = value.strip().strip('"').strip("'")
            except Exception as e:
                # Removed print statement to reduce verbosity
                pass
    
    return env_vars

# Import dependency checking functions directly from dependencies.py
# Use direct import to avoid circular dependency issues
import sys
import importlib.util

# Try to import dependencies module directly
try:
    spec = importlib.util.spec_from_file_location("dependencies", "/projects/src/banyan_extract/utils/dependencies.py")
    dependencies_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dependencies_module)
    has_marker_dependencies = dependencies_module.has_marker_dependencies
    has_nemotronparse_dependencies = dependencies_module.has_nemotronparse_dependencies
except Exception as e:
    # Fallback: create simple dependency checking functions
    def has_marker_dependencies():
        try:
            importlib.import_module('marker_pdf')
            importlib.import_module('surya_ocr')
            return True
        except:
            return False
    
    def has_nemotronparse_dependencies():
        try:
            importlib.import_module('openai')
            return True
        except:
            return False

@pytest.fixture
def test_data_dir():
    """Return the base test data directory."""
    return TEST_DATA_DIR

@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary directory for test outputs using pytest's tmp_path."""
    return tmp_path

@pytest.fixture
def sample_pdf_file(test_data_dir):
    """Return path to a sample PDF file for testing."""
    return test_data_dir / "processors" / "sample.pdf"

@pytest.fixture
def sample_pptx_file(test_data_dir):
    """Return path to a sample PPTX file for testing."""
    # Try to use the docs slides.pptx (which we know exists and has content)
    sample_file = test_data_dir / "docs" / "slides.pptx"
    
    # If the file doesn't exist, skip the test gracefully
    if not sample_file.exists():
        pytest.skip("Sample PPTX file not found for testing")
        
    return sample_file

@pytest.fixture
def sample_json_output(test_data_dir):
    """Return path to a sample JSON output file."""
    return test_data_dir / "outputs" / "sample_output.json"

@pytest.fixture
def rotation_test_pdf():
    """Return path to the rotation test PDF file (sample.pdf)."""
    return TEST_DATA_DIR / "docs" / "sample.pdf"

@pytest.fixture
def rotation_test_pdf_with_shape():
    """Return path to the rotation test PDF file with colored shape (sample_shape.pdf)."""
    return TEST_DATA_DIR / "docs" / "sample_shape.pdf"

@pytest.fixture
def rotation_test_image():
    """Create a test image with distinctive features for rotation testing."""
    from PIL import Image, ImageDraw
    
    # Create a 400x300 image with distinctive colored rectangles
    image = Image.new('RGB', (400, 300), color='white')
    draw = ImageDraw.Draw(image)
    
    # Draw distinctive shapes that will be easy to verify after rotation
    # Top-left: Red rectangle (horizontal)
    draw.rectangle([(50, 50), (250, 100)], fill='red')
    draw.text((60, 60), "TOP-LEFT", fill='black')
    
    # Top-right: Blue rectangle (vertical)  
    draw.rectangle([(350, 50), (380, 250)], fill='blue')
    draw.text((355, 60), "TOP", fill='white')
    draw.text((355, 80), "RIGHT", fill='white')
    
    # Bottom-left: Green square
    draw.rectangle([(50, 200), (150, 300)], fill='green')
    draw.text((60, 210), "BOTTOM", fill='black')
    draw.text((60, 230), "LEFT", fill='black')
    
    # Bottom-right: Yellow rectangle
    draw.rectangle([(250, 200), (380, 280)], fill='yellow')
    draw.text((260, 210), "BOTTOM", fill='black')
    draw.text((260, 230), "RIGHT", fill='black')
    
    return image

@pytest.fixture
def nemoparse_processor():
    """Create a NemoparseProcessor instance for testing."""
    pytest.importorskip("banyan_extract.processor.nemoparse_processor")
    from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
    return NemoparseProcessor()


@pytest.fixture
def configured_nemoparse_processor():
    """Create a configured NemoparseProcessor instance for testing.
    
    This fixture imports the processor, gets configuration from .env file using python-dotenv,
    and creates a configured instance. Skips the test if configuration is missing.
    
    Note: Dependency checking is handled automatically by the @pytest.mark.requires_nemotronparse
    marker and the automatic test filtering system.
    
    Returns:
        Configured NemoparseProcessor instance
    """

    
    # Import the processor with proper error handling
    try:
        from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
    except ImportError as e:
        pytest.skip(f"Failed to import NemoparseProcessor: {e}")
    
    # Get configuration from .env file using python-dotenv
    def get_nemoparse_config_from_dotenv():
        """Get Nemoparse configuration from .env file."""
        # Try to load .env file from project root
        env_path = Path(__file__).parent.parent / ".env"
        
        if not env_path.exists():
            return None
        
        # Load the .env file
        load_result = load_dotenv(env_path)
        
        if not load_result:
            return None
        
        # Get configuration from environment (now loaded from .env)
        endpoint_url = os.environ.get('NEMOPARSE_ENDPOINT', None)
        model_name = os.environ.get('NEMOPARSE_MODEL', None)
        
        return {
            'endpoint_url': endpoint_url,
            'model_name': model_name
        }
    
    config = get_nemoparse_config_from_dotenv()
    
    # Skip the test with a clear message if .env file is missing or configuration is incomplete
    if config is None:
        pytest.skip("Nemoparse configuration missing. .env file not found or could not be loaded.")
    
    if not config['endpoint_url'] or not config['model_name']:
        pytest.skip("Nemoparse configuration missing. .env file must contain NEMOPARSE_ENDPOINT and NEMOPARSE_MODEL.")
    
    # Create and return a configured NemoparseProcessor instance
    return NemoparseProcessor(
        endpoint_url=config['endpoint_url'],
        model_name=config['model_name']
    )

@pytest.fixture
def marker_processor():
    """Create a MarkerProcessor instance for testing."""
    pytest.importorskip("banyan_extract.processor.marker_processor")
    from banyan_extract.processor.marker_processor import MarkerProcessor
    return MarkerProcessor()

@pytest.fixture
def pptx_processor():
    """Create a PptxProcessor instance for testing."""
    pytest.importorskip("banyan_extract.processor.pptx_processor")
    from banyan_extract.processor.pptx_processor import PptxProcessor
    return PptxProcessor()

@pytest.fixture
def papermage_processor():
    """Create a PaperMageProcessor instance for testing."""
    pytest.importorskip("banyan_extract.processor.papermage_processor")
    from banyan_extract.processor.papermage_processor import PaperMageProcessor
    return PaperMageProcessor()


def validate_api_configuration_for_real_mode(config):
    """
    Validate API configuration when using real API mode.
    
    Args:
        config: pytest config object
        
    Raises:
        ValueError: If real API mode is enabled but configuration is missing
    """
    test_mode = config.getoption("--api-test-mode")
    
    if test_mode in ['real', 'auto']:
        endpoint = os.environ.get('NEMOPARSE_ENDPOINT')
        model = os.environ.get('NEMOPARSE_MODEL')
        
        if test_mode == 'real' and (not endpoint or not model):
            raise ValueError(
                "Real API mode requires NEMOPARSE_ENDPOINT and NEMOPARSE_MODEL "
                "environment variables"
            )
        
        # Additional validation for endpoint URL format
        if endpoint and not endpoint.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid endpoint URL format: {endpoint}")

def get_api_endpoint_url():
    """
    Get the API endpoint URL from environment variables with validation.
    
    This function loads environment variables from .env file if available
    before checking the environment variable.
    
    Returns:
        str: Validated API endpoint URL
        
    Raises:
        ValueError: If endpoint URL is invalid or missing
    """
    # Load environment variables from .env file
    load_environment_variables()
    
    endpoint = os.environ.get('NEMOPARSE_ENDPOINT')
    
    if not endpoint:
        raise ValueError("NEMOPARSE_ENDPOINT environment variable not set")
    
    if not endpoint.startswith(('http://', 'https://')):
        raise ValueError(f"Invalid endpoint URL format: {endpoint}")
    
    return endpoint

def get_api_model_name():
    """
    Get the API model name from environment variables with validation.
    
    This function loads environment variables from .env file if available
    before checking the environment variable.
    
    Returns:
        str: Validated API model name
        
    Raises:
        ValueError: If model name is missing
    """
    # Load environment variables from .env file
    load_environment_variables()
    
    model = os.environ.get('NEMOPARSE_MODEL')
    
    if not model:
        raise ValueError("NEMOPARSE_MODEL environment variable not set")
    
    return model


@pytest.fixture
def nemoparse_processor_real(request, api_test_mode):
    """
    Create a NemoparseProcessor instance configured for real API calls.
    
    Only available when api_test_mode is 'real' or 'auto' with proper configuration.
    
    Args:
        request: pytest request object
        api_test_mode: current API test mode
        
    Returns:
        NemoparseProcessor: Configured processor instance
        
    Raises:
        pytest.skip.Exception: If real API calls are disabled or configuration is missing
    """
    if api_test_mode == 'mock':
        pytest.skip("Real API calls disabled (--api-test-mode=mock)")
    
    # Import and configuration logic with enhanced error handling
    try:
        from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
        
        # Get configuration from environment (still needed for API credentials)
        try:
            endpoint_url = get_api_endpoint_url()
            model_name = get_api_model_name()
        except ValueError as e:
            if api_test_mode == 'real':
                pytest.skip(f"Real API calls require valid configuration: {str(e)}")
            else:  # auto mode
                pytest.skip(f"Auto mode: API configuration incomplete ({str(e)}), using mocks")
        
        # Create and return configured processor
        return NemoparseProcessor(endpoint_url=endpoint_url, model_name=model_name)
        
    except ImportError:
        pytest.skip("Nemoparse dependencies not available")
    except Exception as e:
        pytest.skip(f"Failed to create real API processor: {str(e)}")


@pytest.fixture
def nemoparse_processor_auto(request, api_test_mode):
    """
    Create a NemoparseProcessor instance that automatically uses real API calls
    when configured, otherwise falls back to mocks.
    
    This fixture provides a convenient way to test with real API calls when available
    but gracefully falls back to mocks when not configured.
    
    Args:
        request: pytest request object
        api_test_mode: current API test mode
        
    Returns:
        NemoparseProcessor: Configured processor instance
        
    Raises:
        pytest.skip.Exception: If dependencies are not available
    """
    # Only available in auto mode
    if api_test_mode != 'auto':
        pytest.skip(f"Auto processor only available when --api-test-mode=auto")
    
    # Try to create real processor first
    try:
        return nemoparse_processor_real(request, api_test_mode)
    except pytest.skip.Exception:
        # Fall back to regular processor with mocks
        try:
            from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
            return NemoparseProcessor()
        except ImportError:
            pytest.skip("Nemoparse dependencies not available")


@pytest.fixture
def configured_nemoparse_processor_real(request, api_test_mode):
    """
    Create a pre-configured NemoparseProcessor instance for real API calls
    with additional configuration options.
    
    This fixture extends the basic real processor with additional setup
    and configuration for more complex testing scenarios.
    
    Args:
        request: pytest request object
        api_test_mode: current API test mode
        
    Returns:
        NemoparseProcessor: Configured and enhanced processor instance
        
    Raises:
        pytest.skip.Exception: If real API calls are disabled or configuration is missing
    """
    processor = nemoparse_processor_real(request, api_test_mode)
    
    # Additional configuration for real API testing
    # This can be extended with specific configurations as needed
    
    return processor


@pytest.fixture
def real_api_test_data():
    """
    Provide real test data for API testing.
    
    This fixture creates realistic test data that can be used with real API calls.
    It includes sample documents, images, and expected responses.
    
    Returns:
        dict: Dictionary containing real test data for API testing
    """
    from PIL import Image
    import io
    
    # Create real test images
    test_images = {}
    
    # Standard test image
    standard_image = Image.new('RGB', (400, 300), color='white')
    img_byte_arr = io.BytesIO()
    standard_image.save(img_byte_arr, format='PNG')
    test_images['standard'] = img_byte_arr.getvalue()
    
    # Multi-page document images
    multi_page_images = []
    for i in range(3):
        page_image = Image.new('RGB', (400, 300), color=f'lightgray')
        img_byte_arr = io.BytesIO()
        page_image.save(img_byte_arr, format='PNG')
        multi_page_images.append(img_byte_arr.getvalue())
    test_images['multi_page'] = multi_page_images
    
    # Test image with special content
    special_image = Image.new('RGB', (400, 300), color='white')
    # Add some visual elements to make it more realistic
    # (In a real implementation, you might add text, shapes, etc.)
    img_byte_arr = io.BytesIO()
    special_image.save(img_byte_arr, format='PNG')
    test_images['special'] = img_byte_arr.getvalue()
    
    return {
        'images': test_images,
        'expected_responses': {
            'standard': {
                'text': 'Sample document content',
                'elements': ['header', 'paragraph', 'footer']
            },
            'multi_page': {
                'pages': 3,
                'text_per_page': 'Page {i} content'
            }
        }
    }


@pytest.fixture
def api_test_configuration():
    """
    Provide comprehensive API test configuration.
    
    This fixture combines API mode configuration with real API setup
    to provide a complete testing environment.
    
    Args:
        request: pytest request object
        api_test_mode: current API test mode
        
    Returns:
        dict: API test configuration including mode, processor, and status
    """
    def get_configuration(request, api_test_mode):
        config = request.config
        test_mode = config.getoption("--api-test-mode")
        
        # Determine if real API testing is possible
        endpoint_available = bool(os.environ.get('NEMOPARSE_ENDPOINT'))
        model_available = bool(os.environ.get('NEMOPARSE_MODEL'))
        
        real_api_possible = endpoint_available and model_available
        
        # Try to get real processor if possible
        processor = None
        using_real_api = False
        
        if real_api_possible and test_mode in ['real', 'auto']:
            try:
                processor = nemoparse_processor_real(request, api_test_mode)
                using_real_api = True
            except pytest.skip.Exception:
                # Could not create real processor, will use mocks
                pass
        
        # Fall back to regular processor
        if processor is None:
            try:
                from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
                processor = NemoparseProcessor()
                using_real_api = False
            except ImportError:
                pytest.skip("Nemoparse dependencies not available")
        
        return {
            'mode': test_mode,
            'processor': processor,
            'using_real_api': using_real_api,
            'real_api_possible': real_api_possible,
            'endpoint_available': endpoint_available,
            'model_available': model_available
        }
    
    return get_configuration(request, api_test_mode)


def has_all_optional_dependencies():
    """Check if all optional dependencies are available."""
    return has_marker_dependencies() and has_nemotronparse_dependencies()

@pytest.fixture(scope="session")
def marker_available():
    """Fixture that indicates if marker dependencies are available."""
    return has_marker_dependencies()

@pytest.fixture(scope="session")
def nemotronparse_available():
    """Fixture that indicates if nemotronparse dependencies are available."""
    return has_nemotronparse_dependencies()

@pytest.fixture(scope="session")
def all_optional_deps_available():
    """Fixture that indicates if all optional dependencies are available."""
    return has_all_optional_dependencies()


@pytest.fixture(scope="session")
def api_test_mode(request):
    """
    Return the current API test mode from pytest configuration.
    
    Values:
    - 'mock': Use mocked API calls (default)
    - 'real': Use real API calls when available
    - 'auto': Use real API calls if configured, otherwise mock
    
    Returns:
        str: API test mode
    """
    return get_api_test_mode(request)


def get_api_test_mode_from_item(item):
    """
    Get the API test mode from a test item's configuration.
    
    Args:
        item: pytest test item
        
    Returns:
        str: API test mode
    """
    config = item.config
    return config.getoption("--api-test-mode")


def should_skip_test_based_on_markers(item):
    """
    Determine if a test should be skipped based on API test mode and markers.
    
    Args:
        item: pytest test item
        
    Returns:
        tuple: (should_skip, skip_reason) or (False, None)
    """
    config = item.config
    test_mode = config.getoption("--api-test-mode")
    
    has_real_marker = any(marker.name == "real_api" for marker in item.iter_markers())
    has_mock_marker = any(marker.name == "mock_api" for marker in item.iter_markers())
    has_any_marker = any(marker.name == "any_api" for marker in item.iter_markers())
    
    # Determine skip logic
    if has_real_marker and test_mode == "mock":
        return True, f"Test requires real API but --api-test-mode={test_mode}"
    
    if has_mock_marker and test_mode in ["real", "auto"]:
        return True, f"Test requires mock API but --api-test-mode={test_mode}"
    
    # Test can run (either has any_api marker, or no conflicting markers)
    return False, None


def get_api_configuration_status():
    """
    Get the current API configuration status.
    
    This function loads environment variables from .env file if available
    and returns the current API configuration status.
    
    Returns:
        dict: Configuration status including endpoint and model availability
    """
    # Load environment variables from .env file
    load_environment_variables()
    
    # Get current environment variables
    endpoint = os.environ.get('NEMOPARSE_ENDPOINT')
    model = os.environ.get('NEMOPARSE_MODEL')
    
    return {
        'endpoint_available': bool(endpoint),
        'model_available': bool(model),
        'endpoint': endpoint,
        'model': model
    }


def pytest_collection_finish(session):
    """
    Provide summary information about API test configuration after collection.
    
    This hook runs after test collection and provides useful information
    about the API test mode and configuration. Output is conditional based on
    verbosity settings.
    
    Args:
        session: pytest session object
    """
    # Check if we should show detailed output
    verbose_output = session.config.getoption("--verbose-output")
    suppress_output = session.config.getoption("--suppress-output")
    
    # Only show detailed summary if verbose output is requested or suppress mode is disabled
    if not (verbose_output or not suppress_output):
        return
    
    # Get API test mode
    test_mode = session.config.getoption("--api-test-mode")
    
    # Get API configuration status
    config_status = get_api_configuration_status()
    
    # Count tests by marker
    real_api_tests = []
    mock_api_tests = []
    any_api_tests = []
    unmarked_tests = []
    
    for item in session.items:
        has_real = any(marker.name == "real_api" for marker in item.iter_markers())
        has_mock = any(marker.name == "mock_api" for marker in item.iter_markers())
        has_any = any(marker.name == "any_api" for marker in item.iter_markers())
        
        if has_real:
            real_api_tests.append(item)
        elif has_mock:
            mock_api_tests.append(item)
        elif has_any:
            any_api_tests.append(item)
        else:
            unmarked_tests.append(item)
    
    # Report configuration using print (simpler and more reliable)
    print(
        f"\n=== API Test Configuration Summary ==="
        f"\nAPI Test Mode: {test_mode}"
        f"\nReal API Endpoint: {config_status['endpoint_available']} (available: {config_status['endpoint_available']})"
        f"\nReal API Model: {config_status['model_available']} (available: {config_status['model_available']})"
        f"\n\nTest Distribution:"
        f"  Real API Tests: {len(real_api_tests)}"
        f"  Mock API Tests: {len(mock_api_tests)}"
        f"  Any API Tests: {len(any_api_tests)}"
        f"  Unmarked Tests: {len(unmarked_tests)}"
        f"\nTotal Tests: {len(session.items)}"
        f"\n=== End Configuration Summary ===\n"
    )


def pytest_addoption(parser):
    """Add custom command-line options for test filtering and output control.
    
    This function adds command-line options to enable debug logging
    for test filtering decisions and control output verbosity levels.
    """
    parser.addoption(
        "--filter-debug",
        action="store_true",
        default=False,
        help="Enable debug logging for test filtering decisions"
    )
    parser.addoption(
        "--verbose-output",
        action="store_true",
        default=False,
        help="Enable verbose output with detailed dependency and installation information"
    )
    parser.addoption(
        "--suppress-output",
        action="store_true",
        default=True,
        help="Suppress non-essential output (default: True)"
    )
    parser.addoption(
        "--no-suppress-output",
        action="store_false",
        dest="suppress_output",
        help="Show all output (disables --suppress-output)"
    )
    parser.addoption(
        "--api-test-mode",
        action="store",
        default="mock",
        choices=["mock", "real", "auto"],
        help="API test mode: 'mock' (default), 'real', or 'auto'"
    )


def get_api_test_mode(request):
    """
    Get the API test mode from pytest configuration.
    
    Args:
        request: pytest request object
        
    Returns:
        str: API test mode ('mock', 'real', or 'auto')
    """
    config = request.config
    return config.getoption("--api-test-mode")


def pytest_configure(config):
    """Register custom pytest markers and configure logging.
    
    These markers are used to categorize tests based on their dependency requirements:
    - requires_marker: Tests that require marker PDF processing dependencies (marker_pdf, surya_ocr)
    - requires_nemotronparse: Tests that require nemotronparse dependencies (openai)
    - core: Tests that only use core functionality and have no optional dependencies
    
    Note: Tests can use both custom markers and automatic filtering. Custom markers
    take precedence over automatic filtering.
    """
    # Set up logging configuration based on command line options
    setup_test_logging(config)
    
    # Enable debug logging if requested (this will be handled by setup_test_logging)
    if config.getoption("--filter-debug"):
        enable_debug_logging()
    
    config.addinivalue_line(
        "markers",
        "requires_marker: mark test as requiring marker dependencies"
    )
    config.addinivalue_line(
        "markers",
        "requires_nemotronparse: mark test as requiring nemotronparse dependencies"
    )
    config.addinivalue_line(
        "markers",
        "core: mark test as core functionality (no optional dependencies)"
    )
    
    # Add API test mode markers
    config.addinivalue_line(
        "markers",
        "real_api: mark test as requiring real API calls"
    )
    config.addinivalue_line(
        "markers",
        "mock_api: mark test as requiring mocked API calls"
    )
    config.addinivalue_line(
        "markers",
        "any_api: mark test as working with either real or mocked API calls"
    )
    
    # Store verbose output setting in config for use in terminal summary
    config.verbose_output = config.getoption("--verbose-output")
    config.suppress_output = config.getoption("--suppress-output")


def pytest_collection_modifyitems(items, config):
    """Automatically filter tests based on available dependencies and custom markers.
    
    This enhanced function provides more precise filtering by checking both filename
    and path, supports custom markers in addition to automatic filtering, and adds
    debug logging for filtering decisions.
    
    Filtering Logic:
    1. Check for custom markers first (requires_marker, requires_nemotronparse, core)
    2. Apply automatic filtering based on filename and path patterns
    3. Log debug information about filtering decisions
    
    Args:
        items: List of pytest test items
        config: pytest configuration object
    """
    import logging
    import pathlib
    
    # Get logger and configure based on command line option
    logger = logging.getLogger("pytest_filtering")
    
    # Check suppress output setting
    suppress_output = config.getoption("--suppress-output")
    
    # Enable debug logging if --filter-debug flag is set
    if config.getoption("--filter-debug"):
        logger.setLevel(logging.DEBUG)
        
        # Add console handler if not already configured
        if not logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            logger.addHandler(ch)
    elif suppress_output:
        # In suppress output mode, reduce logging to WARNING level to minimize output
        logger.setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.INFO)
    
    # Check dependency availability
    marker_available = has_marker_dependencies()
    nemotronparse_available = has_nemotronparse_dependencies()
    
    # Log dependency status at the start
    logger.info(f"Test filtering - Marker dependencies available: {marker_available}")
    logger.info(f"Test filtering - Nemotronparse dependencies available: {nemotronparse_available}")
    
    for item in items:
        # Convert fspath to Path object to access path components
        path_obj = pathlib.Path(str(item.fspath))
        
        # Get relative path for better logging
        try:
            relative_path = path_obj.relative_to(Path(__file__).parent)
        except ValueError:
            relative_path = path_obj
        
        # Check for custom markers first (highest priority)
        has_marker_marker = any(marker.name == "requires_marker" for marker in item.iter_markers())
        has_nemotronparse_marker = any(marker.name == "requires_nemotronparse" for marker in item.iter_markers())
        has_core_marker = any(marker.name == "core" for marker in item.iter_markers())
        
        # Log marker information
        markers_list = [marker.name for marker in item.iter_markers()]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Test: {relative_path}::{item.name} - Markers: {markers_list}")
        
        # Apply filtering based on custom markers
        if has_marker_marker and not marker_available:
            logger.info(f"Skipping (marker marker): {relative_path}::{item.name}")
            item.add_marker(pytest.mark.skip(reason="marker dependencies not available (custom marker)"))
            continue
            
        if has_nemotronparse_marker and not nemotronparse_available:
            logger.info(f"Skipping (nemotronparse marker): {relative_path}::{item.name}")
            item.add_marker(pytest.mark.skip(reason="nemotronparse dependencies not available (custom marker)"))
            continue
        
        # Apply automatic filtering based on filename and path patterns
        # More precise pattern matching
        file_stem = path_obj.stem.lower()
        file_name = path_obj.name.lower()
        file_path_str = str(path_obj).lower()
        
        # Check for marker-related patterns
        marker_patterns = [
            "marker" in file_stem,
            "marker" in file_name,
            "marker" in file_path_str,
            "marker_" in file_stem,
            "_marker" in file_stem
        ]
        
        # Check for nemotronparse-related patterns
        nemotronparse_patterns = [
            "nemotronparse" in file_stem,
            "nemotronparse" in file_name,
            "nemotronparse" in file_path_str,
            "nemotron_" in file_stem,
            "_nemotron" in file_stem
        ]
        
        # Apply automatic filtering
        if any(marker_patterns) and not marker_available and not has_marker_marker:
            logger.info(f"Skipping (auto marker): {relative_path}::{item.name}")
            item.add_marker(pytest.mark.skip(reason="marker dependencies not available (auto-detected)"))
            continue
        
        if any(nemotronparse_patterns) and not nemotronparse_available and not has_nemotronparse_marker:
             logger.info(f"Skipping (auto nemotronparse): {relative_path}::{item.name}")
             item.add_marker(pytest.mark.skip(reason="nemotronparse dependencies not available (auto-detected)"))
             continue
        
        # Apply API test mode filtering based on markers
        test_mode = config.getoption("--api-test-mode")
        has_real_marker = any(marker.name == "real_api" for marker in item.iter_markers())
        has_mock_marker = any(marker.name == "mock_api" for marker in item.iter_markers())
        has_any_marker = any(marker.name == "any_api" for marker in item.iter_markers())
        
        # Enhanced skip logic with better messaging
        should_skip, skip_reason = should_skip_test_based_on_markers(item)
        
        if should_skip:
            # Provide detailed skip information
            marker_names = [marker.name for marker in item.iter_markers()]
            test_name = f"{relative_path}::{item.name}"
            
            logger.info(f"Skipping API test: {test_name}")
            logger.info(f"  Markers: {', '.join(marker_names) if marker_names else 'None'}")
            logger.info(f"  Mode: {test_mode}")
            logger.info(f"  Reason: {skip_reason}")
            
            item.add_marker(
                pytest.mark.skip(reason=skip_reason)
            )
            continue
            
        # Log tests that will be run with API mode information
        if has_real_marker:
            logger.info(f"Running real API test: {relative_path}::{item.name} (mode: {test_mode})")
        elif has_mock_marker:
            logger.info(f"Running mock API test: {relative_path}::{item.name} (mode: {test_mode})")
        elif has_any_marker:
            logger.info(f"Running any API test: {relative_path}::{item.name} (mode: {test_mode})")
        else:
            logger.debug(f"Running unmarked test: {relative_path}::{item.name} (mode: {test_mode})")
        
        # Log tests that will be run
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Running: {relative_path}::{item.name}")


def enable_debug_logging():
    """Enable debug logging for test filtering.
    
    This function configures logging to show detailed debug information
    about test filtering decisions. It should be called when verbose
    logging is desired.
    
    Returns:
        Configured logger instance
    """
    import logging
    
    logger = logging.getLogger("pytest_filtering")
    logger.setLevel(logging.DEBUG)
    
    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(ch)
    
    return logger


def setup_test_logging(config):
    """Set up logging configuration for tests based on command line options.
    
    Sets default logging level to WARNING to reduce verbosity.
    Only enables DEBUG logging when --filter-debug flag is set.
    
    Args:
        config: pytest configuration object
    """
    import logging
    
    # Set default logging level to WARNING for reduced verbosity
    default_level = logging.WARNING
    
    # Enable DEBUG logging if --filter-debug flag is set
    if config.getoption("--filter-debug"):
        default_level = logging.DEBUG
    
    # Configure root logger
    logging.basicConfig(
        level=default_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Also configure the pytest_filtering logger specifically
    pytest_logger = logging.getLogger("pytest_filtering")
    pytest_logger.setLevel(default_level)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Add enhanced user-friendly terminal summary with comprehensive dependency and test information.
    
    This enhanced summary provides:
    1. Visual indicators (OK/FAIL) for available/missing dependencies
    2. Detailed package breakdown showing individual package status
    3. Version information for installed packages
    4. Comprehensive test execution statistics
    5. Conditional installation guidance (only shown when dependencies are missing)
    6. Simplified helpful tips for advanced usage
    7. Better organization with clear section headers
    
    Output is conditional based on verbosity settings to reduce noise.
    """
    # Clear caches to ensure we get fresh results (in case tests mocked the imports)
    try:
        has_marker_dependencies.cache_clear()
    except Exception:
        pass
    
    try:
        has_nemotronparse_dependencies.cache_clear()
    except Exception:
        pass
    
    # Import additional utilities for enhanced summary
    # Use the same direct import approach to avoid circular dependencies
    try:
        spec = importlib.util.spec_from_file_location("dependencies", "/projects/src/banyan_extract/utils/dependencies.py")
        dependencies_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dependencies_module)
        get_dependency_info = dependencies_module.get_dependency_info
        get_installation_instructions = dependencies_module.get_installation_instructions
    except Exception as e:
        # Fallback implementations
        def get_dependency_info():
            return {
                'marker': {
                    'marker_pdf': {'available': False, 'version': None, 'error': 'Import failed: No module named marker_pdf'},
                    'surya_ocr': {'available': False, 'version': None, 'error': 'Import failed: No module named surya_ocr'}
                },
                'nemotronparse': {
                    'openai': {'available': True, 'version': 'unknown', 'error': None}
                }
            }
        
        def get_installation_instructions():
            return {
                'marker': 'pip install .[marker]',
                'nemotronparse': 'pip install .[nemotronparse]',
                'all': 'pip install .[marker,nemotronparse]'
            }
    
    # Get comprehensive test statistics
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    xfailed = len(terminalreporter.stats.get('xfailed', []))
    xpassed = len(terminalreporter.stats.get('xpassed', []))
    error = len(terminalreporter.stats.get('error', []))
    
    # Calculate total tests (passed + failed + skipped + xfailed + xpassed + error)
    total_tests = passed + failed + skipped + xfailed + xpassed + error
    
    # Calculate success rate
    success_rate = (passed / total_tests * 100) if total_tests > 0 else 100
    
    # Get detailed dependency information
    dependency_info = get_dependency_info()
    installation_instructions = get_installation_instructions()
    
    # Check if verbose output is enabled
    verbose_output = getattr(config, 'verbose_output', False)
    suppress_output = getattr(config, 'suppress_output', True)
    
    # Only show detailed summary if verbose output is requested or suppress mode is disabled
    if not (verbose_output or not suppress_output):
        # Show minimal summary in suppress output mode
        terminalreporter.write_sep("=", "Test Execution Summary")
        terminalreporter.write_line(f"Total: {total_tests}, Passed: {passed}, Failed: {failed}, Skipped: {skipped}")
        if failed == 0 and error == 0:
            terminalreporter.write_line("All tests passed!")
        return
    
    # Write enhanced terminal summary
    terminalreporter.write_sep("=", "Test Execution Summary")
    
    # Test statistics section
    terminalreporter.write_line("Test Statistics:")
    terminalreporter.write_line(f"  Total: {total_tests}")
    terminalreporter.write_line(f"  Passed: {passed} [OK]")
    terminalreporter.write_line(f"  Failed: {failed} [FAIL]")
    terminalreporter.write_line(f"  Skipped: {skipped} [SKIP]")
    terminalreporter.write_line(f"  Expected failures: {xfailed}")
    terminalreporter.write_line(f"  Unexpected passes: {xpassed}")
    terminalreporter.write_line(f"  Errors: {error} [ERROR]")
    terminalreporter.write_line(f"  Success rate: {success_rate:.1f}%")
    
    # Add visual indicator based on test results
    if failed == 0 and error == 0:
        terminalreporter.write_line("  Overall: All tests passed! [SUCCESS]")
    elif failed > 0:
        terminalreporter.write_line("  Overall: Some tests failed [FAIL]")
    elif error > 0:
        terminalreporter.write_line("  Overall: Tests completed with errors [ERROR]")
    
    terminalreporter.write_line("")
    
    # Dependency availability section with visual indicators
    terminalreporter.write_sep("=", "Dependency Availability")
    
    # Marker dependencies
    marker_available = has_marker_dependencies()
    marker_status = "[OK] Available" if marker_available else "[FAIL] Not Available"
    terminalreporter.write_line(f"Marker dependencies: {marker_status}")
    
    # Detailed marker package breakdown
    if 'marker' in dependency_info:
        for package_name, package_info in dependency_info['marker'].items():
            if package_info['available']:
                version_str = f" v{package_info['version']}" if package_info['version'] else ""
                terminalreporter.write_line(f"  [OK] {package_name}{version_str}")
            else:
                error_msg = f" ({package_info['error']})" if package_info['error'] else ""
                terminalreporter.write_line(f"  [FAIL] {package_name}: Not available{error_msg}")
    
    # Nemotronparse dependencies
    nemotronparse_available = has_nemotronparse_dependencies()
    nemotronparse_status = "[OK] Available" if nemotronparse_available else "[FAIL] Not Available"
    terminalreporter.write_line(f"Nemotronparse dependencies: {nemotronparse_status}")
    
    # Detailed nemotronparse package breakdown
    if 'nemotronparse' in dependency_info:
        for package_name, package_info in dependency_info['nemotronparse'].items():
            if package_info['available']:
                version_str = f" v{package_info['version']}" if package_info['version'] else ""
                terminalreporter.write_line(f"  [OK] {package_name}{version_str}")
            else:
                error_msg = f" ({package_info['error']})" if package_info['error'] else ""
                terminalreporter.write_line(f"  [FAIL] {package_name}: Not available{error_msg}")
    
    terminalreporter.write_line("")
    
    # Installation guidance section (conditional based on verbose output)
    if verbose_output or not marker_available or not nemotronparse_available:
        terminalreporter.write_sep("=", "Installation Guidance")
        
        # Provide actionable installation guidance with comments
        if not marker_available or not nemotronparse_available:
            terminalreporter.write_line("To install missing dependencies:")
            
            if not marker_available:
                terminalreporter.write_line(f"  # Marker dependencies (PDF processing)")
                terminalreporter.write_line(f"  {installation_instructions['marker']}")
                if verbose_output:
                    terminalreporter.write_line(f"  # Includes: marker_pdf, surya_ocr")
            
            if not nemotronparse_available:
                terminalreporter.write_line(f"  # Nemotronparse dependencies (AI parsing)")
                terminalreporter.write_line(f"  {installation_instructions['nemotronparse']}")
                if verbose_output:
                    terminalreporter.write_line(f"  # Includes: openai")
            
            if not marker_available and not nemotronparse_available:
                terminalreporter.write_line(f"  # Install all optional dependencies")
                terminalreporter.write_line(f"  {installation_instructions['all']}")
        else:
            terminalreporter.write_line("[OK] All optional dependencies are installed!")
            terminalreporter.write_line("You can run all test suites without restrictions.")
        
        terminalreporter.write_line("")
    
    # Helpful tips section (simplified)
    terminalreporter.write_sep("=", "Helpful Tips")
    
    if failed > 0 or error > 0:
        terminalreporter.write_line("Troubleshooting:")
        terminalreporter.write_line("  * Check test logs for detailed error messages")
        terminalreporter.write_line("  * Run specific tests with: pytest tests/path/to/test.py")
        terminalreporter.write_line("  * Use verbose mode: pytest -v")
        terminalreporter.write_line("  * Enable debug logging: pytest --filter-debug")
    
    if skipped > 0:
        terminalreporter.write_line("Skipped tests:")
        terminalreporter.write_line("  * Some tests were skipped due to missing dependencies")
        terminalreporter.write_line("  * Install missing dependencies to run all tests")
    
    terminalreporter.write_line("Advanced usage:")
    terminalreporter.write_line("  * Run tests with coverage: pytest --cov=src/banyan_extract")
    terminalreporter.write_line("  * Run specific test groups: pytest -m marker")
    terminalreporter.write_line("  * Generate HTML report: pytest --html=report.html")
    terminalreporter.write_line("  * Run only core tests: pytest -m core")
    
    terminalreporter.write_line("")
    
    # Summary footer
    terminalreporter.write_sep("=", "Summary")
    
    if failed == 0 and error == 0:
        terminalreporter.write_line("[SUCCESS] All tests completed successfully!")
        terminalreporter.write_line("Your environment is properly configured.")
    else:
        terminalreporter.write_line("[ERROR] Some tests failed or had errors")
        terminalreporter.write_line("Check the detailed output above for troubleshooting guidance.")
    
    terminalreporter.write_line("Thank you for using banyan-extract!")

# Add more fixtures as needed for common test scenarios
