import sickbeard
from sickbeard.notifiers.generic import Notifier

from lib.pynma import pynma


class NMANotifier(Notifier):

    def _notify(self, title, body, nma_api=None, nma_priority=None, **kwargs):

        nma_api = self._choose(nma_api, sickbeard.NMA_API)
        nma_priority = self._choose(nma_priority, sickbeard.NMA_PRIORITY)

        batch = False

        p = pynma.PyNMA()
        keys = nma_api.split(',')
        p.addkey(keys)

        if 1 < len(keys):
            batch = True

        self._log_debug('Sending notice with priority=%s, batch=%s' % (nma_priority, batch))
        response = p.push('SickGear', title, body, priority=nma_priority, batch_mode=batch)

        result = False
        try:
            if u'200' != response[nma_api][u'code']:
                self._log_error('Notification failed')
            else:
                result = True
        except (StandardError, Exception):
            pass

        return result


notifier = NMANotifier
