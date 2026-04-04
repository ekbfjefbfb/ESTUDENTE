"""
Mathematical Analysis and Optimization Module

Comprehensive mathematical functions with performance analysis, precision validation,
and stress testing capabilities for high-load scenarios.
"""

import math
import time
import asyncio
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable, Any
from decimal import Decimal, getcontext
from dataclasses import dataclass
from enum import Enum
import logging

# Configure decimal precision for financial calculations
getcontext().prec = 10

logger = logging.getLogger(__name__)


class PrecisionMode(str, Enum):
    """Precision modes for mathematical operations"""
    FAST = "fast"        # Native float operations
    PRECISE = "precise"  # Decimal operations
    SAFE = "safe"        # Bounded operations with overflow protection


@dataclass
class PerformanceMetrics:
    """Performance metrics for mathematical operations"""
    operation: str
    execution_time_ms: float
    memory_usage_bytes: int
    cpu_cycles_estimate: int
    complexity: str
    precision_loss: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class StressTestResults:
    """Results from stress testing mathematical functions"""
    function_name: str
    concurrent_requests: int
    total_operations: int
    success_count: int
    failure_count: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    max_memory_usage_mb: float
    throughput_ops_sec: float
    bottleneck_detected: Optional[str] = None
    max_capacity: Optional[int] = None


class MathematicalAnalyzer:
    """
    Comprehensive mathematical analysis and optimization toolkit
    
    Features:
    - Algorithmic complexity analysis (O-notation)
    - Memory and CPU requirements calculation
    - Precision validation for floating-point operations
    - Overflow protection for integer operations
    - Stress testing with concurrent load simulation
    - Performance benchmarking
    """
    
    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.SAFE):
        self.precision_mode = precision_mode
        self._performance_cache = {}
    
    def calculate_distance_haversine(
        self, 
        lat1: float, 
        lng1: float, 
        lat2: float, 
        lng2: float,
        precision_mode: Optional[PrecisionMode] = None
    ) -> float:
        """
        Calculate distance between two points using Haversine formula
        with precision control and performance analysis.
        
        Complexity: O(1) - Constant time
        Memory: O(1) - Constant space
        """
        mode = precision_mode or self.precision_mode
        start_time = time.perf_counter()
        
        try:
            R = 6371000  # Earth radius in meters
            
            if mode == PrecisionMode.PRECISE:
                # Use Decimal for high precision with proper trigonometric functions
                lat1_d = Decimal(lat1)
                lng1_d = Decimal(lng1)
                lat2_d = Decimal(lat2)
                lng2_d = Decimal(lng2)
                
                # Convert to radians using math library then to Decimal
                lat1_rad = Decimal(math.radians(float(lat1_d)))
                lat2_rad = Decimal(math.radians(float(lat2_d)))
                delta_lat = Decimal(math.radians(float(lat2_d - lat1_d)))
                delta_lng = Decimal(math.radians(float(lng2_d - lng1_d)))
                
                # Calculate using Decimal operations with math functions where needed
                sin_half_dlat = Decimal(math.sin(float(delta_lat / 2)))
                sin_half_dlng = Decimal(math.sin(float(delta_lng / 2)))
                cos_lat1 = Decimal(math.cos(float(lat1_rad)))
                cos_lat2 = Decimal(math.cos(float(lat2_rad)))
                
                a = sin_half_dlat ** 2 + cos_lat1 * cos_lat2 * sin_half_dlng ** 2
                sqrt_a = Decimal(math.sqrt(float(a)))
                sqrt_1_minus_a = Decimal(math.sqrt(float(1 - a)))
                c = 2 * Decimal(math.atan2(float(sqrt_a), float(sqrt_1_minus_a)))
                result = float(R * c)
                
            else:
                # Standard floating-point implementation
                lat1_rad = math.radians(lat1)
                lat2_rad = math.radians(lat2)
                delta_lat = math.radians(lat2 - lat1)
                delta_lng = math.radians(lng2 - lng1)
                
                a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                result = R * c
                
                if mode == PrecisionMode.SAFE:
                    # Add bounds checking
                    result = max(0, min(result, 2 * math.pi * R))  # Maximum Earth circumference
            
            execution_time = (time.perf_counter() - start_time) * 1000
            
            # Track performance
            self._track_performance(
                "haversine_distance", 
                execution_time, 
                128,  # Estimated memory usage
                1000,  # Estimated CPU cycles
                "O(1)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Haversine calculation: {e}")
            raise
    
    def cosine_similarity(
        self, 
        vec1: np.ndarray, 
        vec2: np.ndarray,
        precision_mode: Optional[PrecisionMode] = None
    ) -> float:
        """
        Calculate cosine similarity between two vectors
        with precision control and overflow protection.
        
        Complexity: O(n) - Linear with vector size
        Memory: O(n) - Linear with vector size
        """
        mode = precision_mode or self.precision_mode
        start_time = time.perf_counter()
        
        try:
            # Validate input vectors
            if vec1.shape != vec2.shape:
                raise ValueError("Vectors must have the same shape")
            
            if mode == PrecisionMode.PRECISE:
                # High precision using Decimal
                dot_product = Decimal(0)
                norm1 = Decimal(0)
                norm2 = Decimal(0)
                
                for i in range(len(vec1)):
                    v1 = Decimal(vec1[i])
                    v2 = Decimal(vec2[i])
                    dot_product += v1 * v2
                    norm1 += v1 * v1
                    norm2 += v2 * v2
                
                norm1 = norm1.sqrt()
                norm2 = norm2.sqrt()
                
                if norm1 == 0 or norm2 == 0:
                    result = 0.0
                else:
                    result = float(dot_product / (norm1 * norm2))
                    
            else:
                # Standard numpy implementation
                dot_product = np.dot(vec1, vec2)
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
                
                if norm1 == 0 or norm2 == 0:
                    result = 0.0
                else:
                    result = float(dot_product / (norm1 * norm2))
                    
                    if mode == PrecisionMode.SAFE:
                        # Clamp to valid range
                        result = max(-1.0, min(1.0, result))
            
            execution_time = (time.perf_counter() - start_time) * 1000
            memory_usage = vec1.nbytes + vec2.nbytes
            
            # Track performance
            self._track_performance(
                "cosine_similarity", 
                execution_time, 
                memory_usage,
                2000 * len(vec1),  # CPU cycles scale with vector size
                "O(n)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in cosine similarity calculation: {e}")
            raise
    
    def calculate_financial_metrics(
        self,
        fixed_costs: float,
        variable_costs: List[float],
        revenues: List[float],
        precision_mode: Optional[PrecisionMode] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive financial metrics with precision control.
        
        Complexity: O(n) - Linear with number of data points
        Memory: O(n) - Linear with number of data points
        """
        mode = precision_mode or self.precision_mode
        start_time = time.perf_counter()
        
        try:
            n = len(variable_costs)
            if len(revenues) != n:
                raise ValueError("Variable costs and revenues must have same length")
            
            if mode == PrecisionMode.PRECISE:
                # High precision financial calculations
                fixed_costs_d = Decimal(fixed_costs)
                variable_costs_d = [Decimal(vc) for vc in variable_costs]
                revenues_d = [Decimal(rev) for rev in revenues]
                
                total_variable_d = sum(variable_costs_d)
                total_revenue_d = sum(revenues_d)
                total_costs_d = fixed_costs_d + total_variable_d
                
                profit_d = total_revenue_d - total_costs_d
                profit_margin_d = (profit_d / total_revenue_d * 100) if total_revenue_d > 0 else Decimal(0)
                
                # Calculate break-even point
                avg_contribution_margin_d = (
                    (total_revenue_d - total_variable_d) / Decimal(n) 
                    if n > 0 else Decimal(0)
                )
                
                break_even_units_d = (
                    fixed_costs_d / avg_contribution_margin_d 
                    if avg_contribution_margin_d > 0 else Decimal(0)
                )
                
                result = {
                    "total_revenue": float(total_revenue_d),
                    "total_costs": float(total_costs_d),
                    "profit": float(profit_d),
                    "profit_margin_percent": float(profit_margin_d),
                    "break_even_units": float(break_even_units_d),
                    "contribution_margin": float(avg_contribution_margin_d)
                }
                
            else:
                # Standard floating-point implementation
                total_variable = sum(variable_costs)
                total_revenue = sum(revenues)
                total_costs = fixed_costs + total_variable
                
                profit = total_revenue - total_costs
                profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else 0.0
                
                # Calculate break-even point
                avg_contribution_margin = (
                    (total_revenue - total_variable) / n 
                    if n > 0 else 0.0
                )
                
                break_even_units = (
                    fixed_costs / avg_contribution_margin 
                    if avg_contribution_margin > 0 else 0.0
                )
                
                result = {
                    "total_revenue": total_revenue,
                    "total_costs": total_costs,
                    "profit": profit,
                    "profit_margin_percent": profit_margin,
                    "break_even_units": break_even_units,
                    "contribution_margin": avg_contribution_margin
                }
                
                if mode == PrecisionMode.SAFE:
                    result = {
                        k: max(0, v) if k in ["total_revenue", "total_costs", "break_even_units"] else v
                        for k, v in result.items()
                    }
                    result["profit_margin_percent"] = max(-100, min(100, result["profit_margin_percent"]))
            
            execution_time = (time.perf_counter() - start_time) * 1000
            memory_usage = (n * 2 * 8) + 100  # 8 bytes per float, 2 arrays, plus overhead
            
            # Track performance
            self._track_performance(
                "financial_metrics", 
                execution_time, 
                memory_usage,
                500 * n,  # CPU cycles scale with data points
                "O(n)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in financial metrics calculation: {e}")
            raise
    
    def _track_performance(
        self, 
        operation: str, 
        execution_time_ms: float, 
        memory_bytes: int, 
        cpu_cycles: int, 
        complexity: str
    ) -> None:
        """Track performance metrics for mathematical operations"""
        metrics = PerformanceMetrics(
            operation=operation,
            execution_time_ms=execution_time_ms,
            memory_usage_bytes=memory_bytes,
            cpu_cycles_estimate=cpu_cycles,
            complexity=complexity
        )
        
        if operation not in self._performance_cache:
            self._performance_cache[operation] = []
        
        self._performance_cache[operation].append(metrics)
    
    def get_performance_summary(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """Get performance summary for all operations or specific operation"""
        if operation:
            metrics_list = self._performance_cache.get(operation, [])
            if not metrics_list:
                return {}
                
            execution_times = [m.execution_time_ms for m in metrics_list]
            memory_usages = [m.memory_usage_bytes for m in metrics_list]
            
            return {
                "operation": operation,
                "total_calls": len(metrics_list),
                "avg_execution_time_ms": sum(execution_times) / len(execution_times),
                "min_execution_time_ms": min(execution_times),
                "max_execution_time_ms": max(execution_times),
                "avg_memory_bytes": sum(memory_usages) / len(memory_usages),
                "complexity": metrics_list[0].complexity
            }
        else:
            return {
                op: self.get_performance_summary(op)
                for op in self._performance_cache.keys()
            }
    
    async def stress_test_function(
        self,
        func: Callable,
        args: Tuple,
        kwargs: Dict,
        concurrent_requests: int = 1000,
        total_operations: int = 10000
    ) -> StressTestResults:
        """
        Stress test a mathematical function with concurrent requests
        """
        import psutil
        from concurrent.futures import ThreadPoolExecutor
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        results = []
        response_times = []
        success_count = 0
        failure_count = 0
        
        async def _execute_request():
            start_time = time.perf_counter()
            try:
                # Execute function with proper error handling
                if asyncio.iscoroutinefunction(func):
                    await func(*args, **kwargs)
                else:
                    # Run synchronous function in thread pool
                    with ThreadPoolExecutor() as executor:
                        await asyncio.get_event_loop().run_in_executor(
                            executor, func, *args, **kwargs
                        )
                
                execution_time = (time.perf_counter() - start_time) * 1000
                results.append((True, execution_time))
                
            except Exception as e:
                execution_time = (time.perf_counter() - start_time) * 1000
                results.append((False, execution_time))
                logger.error(f"Stress test error: {e}")
        
        # Run concurrent requests
        start_time = time.perf_counter()
        
        semaphore = asyncio.Semaphore(concurrent_requests)
        
        async def _limited_execution():
            async with semaphore:
                await _execute_request()
        
        tasks = []
        for i in range(total_operations):
            tasks.append(_limited_execution())
        
        await asyncio.gather(*tasks)
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Process results
        for success, exec_time in results:
            if success:
                success_count += 1
            else:
                failure_count += 1
            response_times.append(exec_time)
        
        # Calculate statistics
        response_times_sorted = sorted(response_times)
        n = len(response_times)
        
        if n > 0:
            avg_response_time = sum(response_times) / n
            p95_index = int(n * 0.95)
            p99_index = int(n * 0.99)
            
            p95_response_time = response_times_sorted[p95_index] if p95_index < n else response_times_sorted[-1]
            p99_response_time = response_times_sorted[p99_index] if p99_index < n else response_times_sorted[-1]
        else:
            avg_response_time = p95_response_time = p99_response_time = 0
        
        # Measure memory usage
        final_memory = process.memory_info().rss
        max_memory_usage_mb = (final_memory - initial_memory) / (1024 * 1024)
        
        throughput = (success_count / (total_time / 1000)) if total_time > 0 else 0
        
        # Detect bottlenecks
        bottleneck = None
        if avg_response_time > 100:  # More than 100ms average
            bottleneck = "CPU_bound"
        elif max_memory_usage_mb > 100:  # More than 100MB memory
            bottleneck = "Memory_bound"
        elif failure_count > success_count * 0.1:  # More than 10% failures
            bottleneck = "Concurrency_limit"
        
        return StressTestResults(
            function_name=func.__name__,
            concurrent_requests=concurrent_requests,
            total_operations=total_operations,
            success_count=success_count,
            failure_count=failure_count,
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            max_memory_usage_mb=max_memory_usage_mb,
            throughput_ops_sec=throughput,
            bottleneck_detected=bottleneck,
            max_capacity=int(success_count * 0.9)  # 90% of successful operations
        )
    
    def calculate_resource_requirements(
        self,
        data_volume: int,
        operation_complexity: str
    ) -> Dict[str, Any]:
        """
        Calculate memory and CPU requirements for different data volumes
        """
        complexity_factors = {
            "O(1)": {"memory_factor": 1, "cpu_factor": 1},
            "O(log n)": {"memory_factor": 2, "cpu_factor": 3},
            "O(n)": {"memory_factor": 10, "cpu_factor": 10},
            "O(n log n)": {"memory_factor": 15, "cpu_factor": 20},
            "O(n²)": {"memory_factor": 100, "cpu_factor": 100},
            "O(2ⁿ)": {"memory_factor": 1000, "cpu_factor": 1000}
        }
        
        factors = complexity_factors.get(operation_complexity, {"memory_factor": 10, "cpu_factor": 10})
        
        base_memory_kb = 100  # Base memory in KB
        base_cpu_ms = 1      # Base CPU time in ms
        
        memory_required_kb = base_memory_kb * factors["memory_factor"] * (data_volume / 1000)
        cpu_required_ms = base_cpu_ms * factors["cpu_factor"] * (data_volume / 1000)
        
        return {
            "data_volume": data_volume,
            "complexity": operation_complexity,
            "memory_required_kb": memory_required_kb,
            "memory_required_mb": memory_required_kb / 1024,
            "cpu_required_ms": cpu_required_ms,
            "estimated_max_throughput": int(1000 / cpu_required_ms * 1000) if cpu_required_ms > 0 else 0
        }


# Global instance for easy access
math_analyzer = MathematicalAnalyzer()
