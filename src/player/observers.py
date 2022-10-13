class DownloaderObservable:
    def __init__(self):
        self._observers = []

    def subscribe(self, observer):
        self._observers.append(observer)

    def unsubscribe(self, observer):
        self._observers.remove(observer)

    def notify_observers(self):
        for obs in self._observers:
            obs.update()


class DownloaderObservers:
    def __init__(self, observable: DownloaderObservable):
        observable.subscribe(self)

    def update(self):
        ...
