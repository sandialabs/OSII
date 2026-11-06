"""
Unit tests for NemoparseProcessor re-run and temperature flags.

These tests verify the retry logic and temperature parameter handling
during image processing within the NemoparseProcessor class.
"""

from unittest.mock import patch, MagicMock
import pytest

NemoparseProcessor = pytest.importorskip("banyan_extract.processor.nemoparse_processor").NemoparseProcessor


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorRerunAndTemperature:
    """Tests for the temperature and re_run capabilities."""

    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_temperature_passed_correctly(self, mock_run_single):
        """Test that the initial temperature flag is correctly passed to the OCR pass."""
        processor = NemoparseProcessor()
        dummy_image = b"dummy_image_data"
        
        mock_run_single.return_value = MagicMock()
        
        processor._process_image(dummy_image, temperature=0.7)
        
        # Verify the temperature parameter is propagated to the single run function
        mock_run_single.assert_called_once_with(
            dummy_image,
            draw_bboxes=True,
            temperature=0.7,
            page_number=None,
        )

    @patch('banyan_extract.processor.nemoparse_processor.evaluate_extraction')
    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_rerun_disabled(self, mock_run_single, mock_evaluate):
        """Test that re-run logic is entirely skipped when the flag is False."""
        processor = NemoparseProcessor()
        
        processor._process_image(b"image_data", re_run=False)
        
        # The single run should happen once, and evaluation should never occur
        mock_run_single.assert_called_once()
        mock_evaluate.assert_not_called()

    @patch('banyan_extract.processor.nemoparse_processor.evaluate_extraction')
    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_rerun_enabled_initial_pass_good(self, mock_run_single, mock_evaluate):
        """Test that no retries occur if the initial pass is evaluated as satisfactory."""
        # Setup evaluation to return should_rerun=False and a low missed area
        mock_evaluate.return_value = (False, 5.0) 
        
        processor = NemoparseProcessor()
        processor._process_image(b"image_data", re_run=True)
        
        # Should only call the OCR pass once because the first attempt was good
        mock_run_single.assert_called_once()
        mock_evaluate.assert_called_once()

    @patch('banyan_extract.processor.nemoparse_processor.evaluate_extraction')
    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_rerun_enabled_breaks_early_on_success(self, mock_run_single, mock_evaluate):
        """Test that the retry loop breaks early if a retry achieves a successful extraction."""
        # First attempt fails (True), second attempt succeeds (False)
        mock_evaluate.side_effect = [(True, 20.0), (False, 5.0)]
        
        out_initial = MagicMock()
        out_retry1 = MagicMock()
        mock_run_single.side_effect = [out_initial, out_retry1]
        
        processor = NemoparseProcessor()
        result = processor._process_image(b"image_data", re_run=True)
        
        # Verify it broke the loop early after the first retry succeeded
        assert mock_run_single.call_count == 2
        assert mock_evaluate.call_count == 2
        
        # The result returned should be the one from the successful retry
        assert result == out_retry1

    @patch('banyan_extract.processor.nemoparse_processor.evaluate_extraction')
    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_rerun_enabled_exhausts_retries_and_returns_best(self, mock_run_single, mock_evaluate):
        """Test that it tries the maximum allowed times and returns the attempt with the lowest missed area."""
        # All attempts fail the threshold, meaning should_rerun is always True
        # The lowest missed percentage is 12.0 on the second retry attempt
        mock_evaluate.side_effect = [
            (True, 25.0), # Initial pass
            (True, 18.0), # Retry 1
            (True, 12.0), # Retry 2 (This is the best outcome)
            (True, 20.0)  # Retry 3
        ]
        
        out_initial = MagicMock()
        out_retry1 = MagicMock()
        out_retry2 = MagicMock() 
        out_retry3 = MagicMock()
        mock_run_single.side_effect = [out_initial, out_retry1, out_retry2, out_retry3]
        
        processor = NemoparseProcessor()
        result = processor._process_image(b"image_data", re_run=True)
        
        # Verify it completed all possible runs (1 initial + 3 retries)
        assert mock_run_single.call_count == 4
        assert mock_evaluate.call_count == 4
        
        # It should return out_retry2 because it had the lowest missed area (12.0)
        assert result == out_retry2

    @patch('banyan_extract.processor.nemoparse_processor.evaluate_extraction')
    @patch.object(NemoparseProcessor, '_run_single_ocr_pass')
    def test_rerun_temperature_used_in_retries(self, mock_run_single, mock_evaluate):
        """Test that retry attempts switch to using the designated re_run_temp value."""
        # First attempt fails, triggering a retry that succeeds
        mock_evaluate.side_effect = [(True, 30.0), (False, 10.0)]
        
        processor = NemoparseProcessor()
        # Call the internal method directly to explicitly pass re_run_temp
        processor._process_image(b"image_data", temperature=0.0, re_run=True, re_run_temp=0.6)
        
        assert mock_run_single.call_count == 2
        
        # Verify the initial call used the base temperature of 0.0
        mock_run_single.assert_any_call(b"image_data", draw_bboxes=True, temperature=0.0, page_number=None)
        
        # Verify the retry attempt switched to the re_run_temp of 0.6
        mock_run_single.assert_any_call(b"image_data", draw_bboxes=True, temperature=0.6, page_number=None)

