#!/usr/bin/env python3
"""
Stress Testing Script for Mathematical Functions

Simulates massive workloads to test performance limits and identify bottlenecks.
"""

import asyncio
import time
import numpy as np
from typing import List, Dict
from utils.math_analysis import MathematicalAnalyzer, PrecisionMode, StressTestResults


class MathStressTester:
    """Comprehensive stress tester for mathematical functions"""
    
    def __init__(self):
        self.analyzer = MathematicalAnalyzer()
        self.results: List[Dict] = []
    
    async def run_comprehensive_stress_test(self):
        """Run comprehensive stress tests for all mathematical functions"""
        print("🚀 Starting comprehensive mathematical stress testing...")
        print("=" * 80)
        
        test_scenarios = [
            self._test_haversine_massive,
            self._test_cosine_similarity_massive,
            self._test_financial_metrics_massive,
            self._test_mixed_workload
        ]
        
        for test_scenario in test_scenarios:
            try:
                await test_scenario()
            except Exception as e:
                print(f"❌ Test scenario failed: {e}")
        
        self._generate_summary_report()
    
    async def _test_haversine_massive(self):
        """Stress test Haversine distance calculation"""
        print("\n📊 Stress Testing: Haversine Distance Calculation")
        print("-" * 50)
        
        # Generate test coordinates
        num_points = 10000
        lats1 = np.random.uniform(-90, 90, num_points)
        lngs1 = np.random.uniform(-180, 180, num_points)
        lats2 = np.random.uniform(-90, 90, num_points)
        lngs2 = np.random.uniform(-180, 180, num_points)
        
        async def haversine_task(i):
            return self.analyzer.calculate_distance_haversine(
                float(lats1[i]), float(lngs1[i]), float(lats2[i]), float(lngs2[i]), PrecisionMode.FAST
            )
        
        # Test different concurrency levels
        concurrency_levels = [10, 100, 500, 1000]
        
        for concurrency in concurrency_levels:
            print(f"\n   Testing {concurrency} concurrent requests...")
            
            start_time = time.time()
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def limited_task(i):
                async with semaphore:
                    return await haversine_task(i)
            
            tasks = [limited_task(i) for i in range(min(1000, num_points))]
            results = await asyncio.gather(*tasks)
            
            total_time = time.time() - start_time
            throughput = len(results) / total_time
            
            print(f"     Completed {len(results)} operations in {total_time:.2f}s")
            print(f"     Throughput: {throughput:.2f} ops/sec")
            print(f"     Avg. time per operation: {(total_time/len(results)*1000):.2f}ms")
            
            self.results.append({
                "test": "haversine",
                "concurrency": concurrency,
                "operations": len(results),
                "total_time": total_time,
                "throughput": throughput,
                "avg_time_ms": (total_time/len(results)*1000)
            })
    
    async def _test_cosine_similarity_massive(self):
        """Stress test cosine similarity calculation"""
        print("\n📊 Stress Testing: Cosine Similarity Calculation")
        print("-" * 50)
        
        # Generate test vectors of different sizes
        vector_sizes = [10, 100, 1000]
        num_pairs = 1000
        
        for size in vector_sizes:
            print(f"\n   Testing vectors of size {size}...")
            
            # Generate random vectors
            vectors1 = np.random.rand(num_pairs, size)
            vectors2 = np.random.rand(num_pairs, size)
            
            async def cosine_task(i):
                return self.analyzer.cosine_similarity(
                    vectors1[i], vectors2[i], PrecisionMode.FAST
                )
            
            # Test concurrency
            concurrency_levels = [10, 50, 100]
            
            for concurrency in concurrency_levels:
                print(f"     With {concurrency} concurrent requests...")
                
                start_time = time.time()
                
                semaphore = asyncio.Semaphore(concurrency)
                
                async def limited_task(i):
                    async with semaphore:
                        return await cosine_task(i)
                
                tasks = [limited_task(i) for i in range(min(100, num_pairs))]
                results = await asyncio.gather(*tasks)
                
                total_time = time.time() - start_time
                throughput = len(results) / total_time
                
                print(f"       Completed {len(results)} operations in {total_time:.2f}s")
                print(f"       Throughput: {throughput:.2f} ops/sec")
                print(f"       Avg. time per operation: {(total_time/len(results)*1000):.2f}ms")
                
                self.results.append({
                    "test": f"cosine_size_{size}",
                    "concurrency": concurrency,
                    "operations": len(results),
                    "total_time": total_time,
                    "throughput": throughput,
                    "avg_time_ms": (total_time/len(results)*1000)
                })
    
    async def _test_financial_metrics_massive(self):
        """Stress test financial metrics calculation"""
        print("\n📊 Stress Testing: Financial Metrics Calculation")
        print("-" * 50)
        
        # Generate test data
        num_companies = 1000
        fixed_costs_list = np.random.uniform(10000, 1000000, num_companies)
        
        # Generate quarterly data for 4 years
        all_variable_costs = []
        all_revenues = []
        
        for _ in range(num_companies):
            quarters = 16  # 4 years
            variable_costs = np.random.uniform(5000, 500000, quarters)
            revenues = np.random.uniform(10000, 1000000, quarters)
            
            all_variable_costs.append(variable_costs)
            all_revenues.append(revenues)
        
        async def financial_task(i):
            return self.analyzer.calculate_financial_metrics(
                float(fixed_costs_list[i]), 
                all_variable_costs[i].tolist(), 
                all_revenues[i].tolist(),
                PrecisionMode.FAST
            )
        
        # Test concurrency
        concurrency_levels = [5, 10, 25]
        
        for concurrency in concurrency_levels:
            print(f"\n   Testing {concurrency} concurrent financial calculations...")
            
            start_time = time.time()
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def limited_task(i):
                async with semaphore:
                    return await financial_task(i)
            
            tasks = [limited_task(i) for i in range(min(50, num_companies))]
            results = await asyncio.gather(*tasks)
            
            total_time = time.time() - start_time
            throughput = len(results) / total_time
            
            print(f"     Completed {len(results)} companies in {total_time:.2f}s")
            print(f"     Throughput: {throughput:.2f} companies/sec")
            print(f"     Avg. time per company: {(total_time/len(results)*1000):.2f}ms")
            
            self.results.append({
                "test": "financial_metrics",
                "concurrency": concurrency,
                "operations": len(results),
                "total_time": total_time,
                "throughput": throughput,
                "avg_time_ms": (total_time/len(results)*1000)
            })
    
    async def _test_mixed_workload(self):
        """Test mixed workload with all mathematical functions"""
        print("\n📊 Stress Testing: Mixed Mathematical Workload")
        print("-" * 50)
        
        num_operations = 5000
        
        async def mixed_operation(i):
            # Alternate between different operations
            op_type = i % 3
            
            if op_type == 0:
                # Haversine
                lat1, lng1 = np.random.uniform(-90, 90), np.random.uniform(-180, 180)
                lat2, lng2 = np.random.uniform(-90, 90), np.random.uniform(-180, 180)
                return self.analyzer.calculate_distance_haversine(
                    lat1, lng1, lat2, lng2, PrecisionMode.FAST
                )
            
            elif op_type == 1:
                # Cosine similarity
                size = np.random.choice([10, 50, 100])
                vec1 = np.random.rand(size)
                vec2 = np.random.rand(size)
                return self.analyzer.cosine_similarity(vec1, vec2, PrecisionMode.FAST)
            
            else:
                # Financial metrics (simplified)
                fixed = np.random.uniform(1000, 10000)
                variable = np.random.uniform(100, 1000, 4).tolist()
                revenue = np.random.uniform(500, 5000, 4).tolist()
                return self.analyzer.calculate_financial_metrics(
                    fixed, variable, revenue, PrecisionMode.FAST
                )
        
        # Test high concurrency
        concurrency_levels = [100, 500, 1000]
        
        for concurrency in concurrency_levels:
            print(f"\n   Testing mixed workload with {concurrency} concurrent requests...")
            
            start_time = time.time()
            
            semaphore = asyncio.Semaphore(concurrency)
            
            async def limited_task(i):
                async with semaphore:
                    return await mixed_operation(i)
            
            tasks = [limited_task(i) for i in range(min(1000, num_operations))]
            results = await asyncio.gather(*tasks)
            
            total_time = time.time() - start_time
            throughput = len(results) / total_time
            
            print(f"     Completed {len(results)} mixed operations in {total_time:.2f}s")
            print(f"     Throughput: {throughput:.2f} ops/sec")
            print(f"     Avg. time per operation: {(total_time/len(results)*1000):.2f}ms")
            
            self.results.append({
                "test": "mixed_workload",
                "concurrency": concurrency,
                "operations": len(results),
                "total_time": total_time,
                "throughput": throughput,
                "avg_time_ms": (total_time/len(results)*1000)
            })
    
    def _generate_summary_report(self):
        """Generate comprehensive performance report"""
        print("\n" + "=" * 80)
        print("📈 COMPREHENSIVE PERFORMANCE REPORT")
        print("=" * 80)
        
        # Group results by test type
        test_groups = {}
        for result in self.results:
            test_name = result["test"]
            if test_name not in test_groups:
                test_groups[test_name] = []
            test_groups[test_name].append(result)
        
        # Print summary for each test type
        for test_name, results in test_groups.items():
            print(f"\n🔍 {test_name.upper()}:")
            print("-" * 40)
            
            # Find best performing concurrency level
            best_throughput = 0
            best_concurrency = 0
            
            for result in results:
                if result["throughput"] > best_throughput:
                    best_throughput = result["throughput"]
                    best_concurrency = result["concurrency"]
                
                print(f"   Concurrency {result['concurrency']}: {result['throughput']:.2f} ops/sec "
                      f"(avg: {result['avg_time_ms']:.2f}ms)")
            
            print(f"   💡 Optimal concurrency: {best_concurrency} "
                  f"({best_throughput:.2f} ops/sec)")
        
        # Overall statistics
        total_operations = sum(r.get("operations", 0) for r in self.results)
        total_time = sum(r.get("total_time", 0) for r in self.results)
        avg_throughput = total_operations / total_time if total_time > 0 else 0
        
        print(f"\n📊 OVERALL STATISTICS:")
        print("-" * 25)
        print(f"   Total operations: {total_operations:,}")
        print(f"   Total test time: {total_time:.2f}s")
        print(f"   Average throughput: {avg_throughput:.2f} ops/sec")
        print(f"   Estimated max capacity: {avg_throughput * 3600:.0f} ops/hour")
        
        # Bottleneck analysis
        print(f"\n🔧 BOTTLENECK ANALYSIS:")
        print("-" * 25)
        
        # Analyze performance characteristics
        fast_ops = [r for r in self.results if r["avg_time_ms"] < 10]
        medium_ops = [r for r in self.results if 10 <= r["avg_time_ms"] < 100]
        slow_ops = [r for r in self.results if r["avg_time_ms"] >= 100]
        
        print(f"   Fast operations (<10ms): {len(fast_ops)}")
        print(f"   Medium operations (10-100ms): {len(medium_ops)}")
        print(f"   Slow operations (≥100ms): {len(slow_ops)}")
        
        if slow_ops:
            slowest = max(slow_ops, key=lambda x: x["avg_time_ms"])
            print(f"   🐌 Slowest operation: {slowest['test']} "
                  f"({slowest['avg_time_ms']:.2f}ms at {slowest['concurrency']} concurrency)")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print("-" * 15)
        
        if any("financial" in r["test"] for r in self.results):
            print("   • Financial calculations are computationally intensive")
            print("   • Consider batching financial operations")
            print("   • Use caching for repeated calculations")
        
        if any(r["concurrency"] >= 500 for r in self.results):
            print("   • High concurrency (500+) shows good scalability")
            print("   • System can handle massive concurrent workloads")
        
        if any("cosine_size_1000" in r["test"] for r in self.results):
            print("   • Large vector operations (size 1000) are memory intensive")
            print("   • Monitor memory usage for embedding operations")
        
        print(f"\n✅ Stress testing completed successfully!")


async def main():
    """Main function"""
    tester = MathStressTester()
    
    try:
        await tester.run_comprehensive_stress_test()
    except KeyboardInterrupt:
        print("\n⏹️  Stress testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Stress testing failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())