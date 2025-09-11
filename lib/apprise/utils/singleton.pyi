from _typeshed import Incomplete

class Singleton(type):
    _instances: Incomplete
    def __call__(cls, *args, **kwargs): ...
