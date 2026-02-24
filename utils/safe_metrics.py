"""
Wrapper temporal para métricas Prometheus que evita errores de duplicación
"""

import logging

logger = logging.getLogger(__name__)

class SafeMetric:
    """Wrapper que evita errores de métricas"""
    
    def __init__(self, name=None):
        self.name = name or "default"
    
    def counter(self, name, description, labels=None):
        """Crea counter mock"""
        return MockMetric(name)
    
    def histogram(self, name, description, labels=None, buckets=None):
        """Crea histogram mock"""
        return MockMetric(name)
    
    def gauge(self, name, description, labels=None):
        """Crea gauge mock"""
        return MockMetric(name)

class MockMetric:
    """Métrica mock"""
    
    def __init__(self, name):
        self.name = name
    
    def inc(self, labels=None, *args, **kwargs):
        """Mock increment"""
        return self
    
    def observe(self, value, labels=None, *args, **kwargs):
        """Mock observe"""
        return self
    
    def set(self, value, labels=None, *args, **kwargs):
        """Mock set"""
        return self
    
    def labels(self, *args, **kwargs):
        """Mock labels - retorna self para permitir chaining"""
        return self
    
    def dec(self, labels=None, *args, **kwargs):
        """Mock decrement"""
        return self

def Counter(name, description, labels=None, **kwargs):
    """Mock Counter"""
    return SafeMetric(name)

def Histogram(name, description, labels=None, **kwargs):
    """Mock Histogram"""
    return SafeMetric(name)

def Gauge(name, description, labels=None, **kwargs):
    """Mock Gauge"""
    return SafeMetric(name)