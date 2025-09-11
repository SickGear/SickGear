from . import notifier

__all__ = ['mini', 'GrowlNotifier']

class GrowlNotifier(notifier.GrowlNotifier):
    def __init__(self, *args, **kwargs) -> None: ...

def mini(description, **kwargs) -> None: ...
