"""
Comprehensive test suite for mathematical analysis functions

Tests precision, performance, and stress capabilities of mathematical operations
"""

import pytest
import asyncio
import numpy as np
from decimal import Decimal
from utils.math_analysis import (
    MathematicalAnalyzer, 
    PrecisionMode, 
    PerformanceMetrics,
    StressTestResults
)


class TestMathematicalAnalyzer:
    """Test suite for MathematicalAnalyzer class"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = MathematicalAnalyzer()
        
    def test_haversine_distance_basic(self):
        """Test basic Haversine distance calculation"""
        # Test coordinates for known distances
        result = self.analyzer.calculate_distance_haversine(
            40.7128, -74.0060,  # New York
            34.0522, -118.2437,  # Los Angeles
            PrecisionMode.FAST
        )
        
        # Should be approximately 3940 km
        assert 3900000 < result < 4000000
        
    def test_haversine_distance_precision_modes(self):
        """Test Haversine distance with different precision modes"""
        coords = (40.7128, -74.0060, 34.0522, -118.2437)
        
        fast_result = self.analyzer.calculate_distance_haversine(*coords, PrecisionMode.FAST)
        safe_result = self.analyzer.calculate_distance_haversine(*coords, PrecisionMode.SAFE)
        precise_result = self.analyzer.calculate_distance_haversine(*coords, PrecisionMode.PRECISE)
        
        # All results should be close to each other
        assert abs(fast_result - safe_result) < 1000  # Within 1km
        assert abs(safe_result - precise_result) < 1000
        
    def test_haversine_edge_cases(self):
        """Test Haversine with edge cases"""
        # Same point
        result = self.analyzer.calculate_distance_haversine(
            40.7128, -74.0060, 
            40.7128, -74.0060,
            PrecisionMode.SAFE
        )
        assert result == 0.0
        
        # Antipodal points (should be ~20000 km)
        result = self.analyzer.calculate_distance_haversine(
            0, 0,  # Equator prime meridian
            0, 180,  # Opposite side
            PrecisionMode.SAFE
        )
        assert 19900000 < result < 20100000
        
    def test_cosine_similarity_basic(self):
        """Test basic cosine similarity"""
        vec1 = np.array([1, 2, 3])
        vec2 = np.array([1, 2, 3])
        
        result = self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.FAST)
        assert abs(result - 1.0) < 1e-10  # Should be exactly 1 for identical vectors
        
        # Orthogonal vectors
        vec3 = np.array([1, 0, 0])
        vec4 = np.array([0, 1, 0])
        
        result = self.analyzer.cosine_similarity(vec3, vec4, PrecisionMode.FAST)
        assert abs(result) < 1e-10  # Should be 0 for orthogonal vectors
        
    def test_cosine_similarity_precision_modes(self):
        """Test cosine similarity with different precision modes"""
        vec1 = np.array([1.23456789, 2.34567890, 3.45678901])
        vec2 = np.array([1.23456789, 2.34567890, 3.45678901])
        
        fast_result = self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.FAST)
        safe_result = self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.SAFE)
        precise_result = self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.PRECISE)
        
        # All should be very close to 1.0
        assert abs(fast_result - 1.0) < 1e-10
        assert abs(safe_result - 1.0) < 1e-10
        assert abs(precise_result - 1.0) < 1e-10
        
    def test_cosine_similarity_zero_vectors(self):
        """Test cosine similarity with zero vectors"""
        vec1 = np.array([0, 0, 0])
        vec2 = np.array([1, 2, 3])
        
        result = self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.SAFE)
        assert result == 0.0
        
    def test_financial_metrics_basic(self):
        """Test basic financial metrics calculation"""
        fixed_costs = 1000.0
        variable_costs = [200.0, 300.0, 400.0]
        revenues = [500.0, 600.0, 700.0]
        
        result = self.analyzer.calculate_financial_metrics(
            fixed_costs, variable_costs, revenues, PrecisionMode.FAST
        )
        
        assert result["total_revenue"] == 1800.0
        assert result["total_costs"] == 1000.0 + 900.0
        assert result["profit"] == 1800.0 - 1900.0
        
    def test_financial_metrics_precision_modes(self):
        """Test financial metrics with different precision modes"""
        fixed_costs = 1000.0
        variable_costs = [200.123456, 300.234567, 400.345678]
        revenues = [500.456789, 600.567890, 700.678901]
        
        fast_result = self.analyzer.calculate_financial_metrics(
            fixed_costs, variable_costs, revenues, PrecisionMode.FAST
        )
        
        precise_result = self.analyzer.calculate_financial_metrics(
            fixed_costs, variable_costs, revenues, PrecisionMode.PRECISE
        )
        
        # Results should be very close
        assert abs(fast_result["total_revenue"] - precise_result["total_revenue"]) < 1e-6
        assert abs(fast_result["profit"] - precise_result["profit"]) < 1e-6
        
    def test_financial_metrics_edge_cases(self):
        """Test financial metrics with edge cases"""
        # Zero revenue
        result = self.analyzer.calculate_financial_metrics(
            1000.0, [200.0, 300.0], [0.0, 0.0], PrecisionMode.SAFE
        )
        
        assert result["total_revenue"] == 0.0
        assert result["profit"] == -1500.0  # -(1000 + 200 + 300)
        assert result["profit_margin_percent"] == 0.0
        
        # High profit margin
        result = self.analyzer.calculate_financial_metrics(
            1000.0, [200.0], [5000.0], PrecisionMode.SAFE
        )
        
        assert result["profit"] == 3800.0
        assert result["profit_margin_percent"] == 76.0  # 3800/5000 * 100
        
    def test_performance_tracking(self):
        """Test performance metrics tracking"""
        # Execute some operations
        for _ in range(5):
            self.analyzer.calculate_distance_haversine(
                40.7128, -74.0060, 34.0522, -118.2437, PrecisionMode.FAST
            )
        
        for _ in range(3):
            vec1 = np.array([1, 2, 3])
            vec2 = np.array([4, 5, 6])
            self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.FAST)
        
        # Check performance summary
        summary = self.analyzer.get_performance_summary()
        
        assert "haversine_distance" in summary
        assert "cosine_similarity" in summary
        assert summary["haversine_distance"]["total_calls"] == 5
        assert summary["cosine_similarity"]["total_calls"] == 3
        
    def test_resource_requirements_calculation(self):
        """Test resource requirements calculation"""
        # Test different complexities
        requirements_o1 = self.analyzer.calculate_resource_requirements(1000, "O(1)")
        requirements_on = self.analyzer.calculate_resource_requirements(1000, "O(n)")
        requirements_on2 = self.analyzer.calculate_resource_requirements(1000, "O(n²)")
        
        # Higher complexity should require more resources
        assert requirements_on["cpu_required_ms"] > requirements_o1["cpu_required_ms"]
        assert requirements_on2["cpu_required_ms"] > requirements_on["cpu_required_ms"]
        
        assert requirements_on["memory_required_kb"] > requirements_o1["memory_required_kb"]
        assert requirements_on2["memory_required_kb"] > requirements_on["memory_required_kb"]
        
    @pytest.mark.asyncio
    async def test_stress_test_fast_function(self):
        """Test stress testing with a fast function"""
        def fast_operation():
            return sum(range(1000))
        
        results = await self.analyzer.stress_test_function(
            fast_operation, (), {}, concurrent_requests=10, total_operations=100
        )
        
        assert isinstance(results, StressTestResults)
        assert results.success_count > 0
        assert results.avg_response_time_ms < 100  # Should be very fast
        assert results.throughput_ops_sec > 10  # Should have good throughput
        
    @pytest.mark.asyncio
    async def test_stress_test_haversine(self):
        """Test stress testing with Haversine function"""
        results = await self.analyzer.stress_test_function(
            self.analyzer.calculate_distance_haversine,
            (40.7128, -74.0060, 34.0522, -118.2437, PrecisionMode.FAST),
            {},
            concurrent_requests=5,
            total_operations=20
        )
        
        assert isinstance(results, StressTestResults)
        assert results.success_count > 0
        assert results.failure_count == 0  # Should not fail
        
    def test_precision_validation_haversine(self):
        """Test precision validation for Haversine"""
        # Test with very close coordinates
        result_fast = self.analyzer.calculate_distance_haversine(
            40.7128000001, -74.0060000001,
            40.7128000002, -74.0060000002,
            PrecisionMode.FAST
        )
        
        result_precise = self.analyzer.calculate_distance_haversine(
            40.7128000001, -74.0060000001,
            40.7128000002, -74.0060000002,
            PrecisionMode.PRECISE
        )
        
        # Both should give very small distances
        assert 0 < result_fast < 1.0  # Less than 1 meter
        assert 0 < result_precise < 1.0
        
        # Precise mode should give more consistent results for micro-distances
        # (though both should be very close)
        
    def test_overflow_protection(self):
        """Test overflow protection in safe mode"""
        # Test with extremely large numbers that could cause overflow
        try:
            result = self.analyzer.calculate_distance_haversine(
                90.0, 0.0, -90.0, 180.0,  # Maximum possible distance
                PrecisionMode.SAFE
            )
            
            # Should be valid and within Earth's circumference
            assert 0 <= result <= 40000000  # Earth circumference ~40,000 km
            
        except Exception as e:
            pytest.fail(f"Overflow protection failed: {e}")


class TestPerformanceAnalysis:
    """Performance analysis tests"""
    
    def test_algorithmic_complexity_analysis(self):
        """Test algorithmic complexity analysis"""
        analyzer = MathematicalAnalyzer()
        
        # Test O(1) complexity
        for n in [1, 10, 100, 1000]:
            analyzer.calculate_distance_haversine(0, 0, 1, 1, PrecisionMode.FAST)
        
        haversine_perf = analyzer.get_performance_summary("haversine_distance")
        assert haversine_perf["complexity"] == "O(1)"
        
        # Test O(n) complexity
        sizes = [10, 100, 1000]
        for size in sizes:
            vec1 = np.ones(size)
            vec2 = np.ones(size)
            analyzer.cosine_similarity(vec1, vec2, PrecisionMode.FAST)
        
        cosine_perf = analyzer.get_performance_summary("cosine_similarity")
        assert cosine_perf["complexity"] == "O(n)"
        
    def test_memory_usage_analysis(self):
        """Test memory usage analysis"""
        analyzer = MathematicalAnalyzer()
        
        # Small vectors
        vec_small1 = np.ones(10)
        vec_small2 = np.ones(10)
        analyzer.cosine_similarity(vec_small1, vec_small2, PrecisionMode.FAST)
        
        # Large vectors
        vec_large1 = np.ones(1000)
        vec_large2 = np.ones(1000)
        analyzer.cosine_similarity(vec_large1, vec_large2, PrecisionMode.FAST)
        
        cosine_perf = analyzer.get_performance_summary("cosine_similarity")
        
        # Memory usage should be reasonable
        assert cosine_perf["avg_memory_bytes"] > 80  # At least 80 bytes for small vectors
        assert cosine_perf["avg_memory_bytes"] < 20000  # Less than 20KB for large vectors


if __name__ == "__main__":
    # Run basic tests
    test_suite = TestMathematicalAnalyzer()
    test_suite.setup_method()
    
    print("Running basic tests...")
    test_suite.test_haversine_distance_basic()
    test_suite.test_cosine_similarity_basic()
    test_suite.test_financial_metrics_basic()
    test_suite.test_performance_tracking()
    
    print("All basic tests passed!")
    
    # Run performance analysis
    perf_test = TestPerformanceAnalysis()
    perf_test.test_algorithmic_complexity_analysis()
    perf_test.test_memory_usage_analysis()
    
    print("All performance tests passed!")
    
    print("✅ All tests completed successfully!")