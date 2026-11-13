"""Cancelamento cooperativo de uma execução e exclusão mútua com a gravação."""

from contextlib import contextmanager
from threading import Event, Lock


class SimulationCancelled(Exception):
    """A execução foi cancelada antes de persistir seu resultado."""


class Cancellation:
    """Sincroniza o pedido de cancelamento com a publicação dos resultados.

    Se a publicação já começou, o pedido chega tarde e retorna False. O lock
    cobre as duas gravações para que um cancelamento aceito não deixe metade
    do resultado publicado. A verificação no motor não depende de HTTP.
    """

    def __init__(self) -> None:
        self._event = Event()
        self._lock = Lock()
        self._committed = False

    def check(self) -> None:
        if self._event.is_set():
            raise SimulationCancelled()

    def cancel(self) -> bool:
        with self._lock:
            if self._committed:
                return False
            self._event.set()
            return True

    @contextmanager
    def commit(self):
        with self._lock:
            self.check()
            self._committed = True
            yield
