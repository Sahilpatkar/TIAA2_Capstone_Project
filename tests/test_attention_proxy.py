"""Tests for attention_proxy.py -- investor attention wrapper."""

from unittest.mock import patch

import pytest

from tiaa.analysis.attention_proxy import get_attention_proxy


class TestGetAttentionProxy:
    @patch("tiaa.analysis.attention_proxy.compute_volume_ratio")
    def test_delegates_to_volume_ratio(self, mock_volume):
        mock_volume.return_value = 1.35
        result = get_attention_proxy("AAPL", "2024-11-01")
        assert result == 1.35
        mock_volume.assert_called_once_with("AAPL", "2024-11-01")

    @patch("tiaa.analysis.attention_proxy.compute_volume_ratio")
    def test_none_passthrough(self, mock_volume):
        mock_volume.return_value = None
        result = get_attention_proxy("AAPL", "2024-11-01")
        assert result is None
