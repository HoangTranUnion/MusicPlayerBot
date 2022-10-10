class DownloaderObservable:
    def __init__(self):
        self._observers = []

    def subscribe(self, observer):
        self._observers.append(observer)

    def notify_observers(self):
        for obs in self._observers:
            obs.notify()


class DownloaderObservers:
    def __init__(self, observable: DownloaderObservable):
        observable.subscribe(self)

    def notify(self):
        ...
