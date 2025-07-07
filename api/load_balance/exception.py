
# 自定义异常类型
class LoadBalancerError(Exception): pass
class NoAvailableInstanceError(LoadBalancerError): pass
class RequestTimeoutError(LoadBalancerError): pass
class LimitExceededError(LoadBalancerError): pass
class ServiceError(LoadBalancerError): pass
class MaxRetriesExceededError(LoadBalancerError): pass