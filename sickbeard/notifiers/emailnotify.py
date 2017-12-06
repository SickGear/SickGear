# Authors:
# Derek Battams <derek@battams.ca>
# Pedro Jose Pereira Vieito (@pvieito) <pvieito@gmail.com>
#
# URL: https://github.com/sickgear/sickgear
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
import re
import smtplib

import sickbeard
from sickbeard import db
from sickbeard.notifiers.generic import Notifier, notify_strings


class EmailNotifier(Notifier):

    def __init__(self):
        super(EmailNotifier, self).__init__()

        self.last_err = None

    def _sendmail(self, host, port, smtp_from, use_tls, user, pwd, to, msg, smtp_debug=False):

        use_tls = 1 == sickbeard.helpers.tryInt(use_tls)
        login = any(user) and any(pwd)
        self._log_debug(u'Sendmail HOST: %s; PORT: %s; LOGIN: %s, TLS: %s, USER: %s, FROM: %s, TO: %s' % (
            host, port, login, use_tls, user, smtp_from, to))

        try:
            srv = smtplib.SMTP(host, int(port))
            if smtp_debug:
                srv.set_debuglevel(1)

            if use_tls or login:
                srv.ehlo()
                self._log_debug(u'Sent initial EHLO command')

                if use_tls:
                    srv.starttls()
                    srv.ehlo()
                    self._log_debug(u'Sent STARTTLS and EHLO command')

                if login:
                    srv.login(user, pwd)
                    self._log_debug(u'Sent LOGIN command')

            srv.sendmail(smtp_from, to, msg.as_string())
            srv.quit()

        except Exception as e:
            self.last_err = '%s' % e
            return False

        return True

    @staticmethod
    def _get_recipients(show_name=None):

        email_list = []

        # Grab the global recipients
        if sickbeard.EMAIL_LIST:
            for email_address in sickbeard.EMAIL_LIST.split(','):
                if any(email_address.strip()):
                    email_list.append(email_address)

        # Grab the recipients for the show
        if None is not show_name:
            my_db = db.DBConnection()
            for result in my_db.select('SELECT notify_list FROM tv_shows WHERE show_name = ?', (show_name,)):
                if result['notify_list']:
                    for email_address in result['notify_list'].split(','):
                        if any(email_address.strip()):
                            email_list.append(email_address)

        return list(set(email_list))

    def _notify(self, title, body, lang='', extra='', **kwargs):

        show = body.split(' - ')[0]
        to = self._get_recipients(show)
        if not any(to):
            self._log_warning(u'No email recipients to notify, skipping')
            return

        self._log_debug(u'Email recipients to notify: %s' % to)

        try:
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(
                '<body style="font-family:Helvetica, Arial, sans-serif;">' +
                '<h3>SickGear Notification - %s</h3>\n' % title +
                '<p>Show: <b>' + show.encode('ascii', 'xmlcharrefreplace') +
                '</b></p>\n<p>Episode: <b>' +
                unicode(re.search('.+ - (.+?-.+) -.+', body).group(1)).encode('ascii', 'xmlcharrefreplace') +
                extra +
                '</b></p>\n\n' +
                '<footer style="margin-top:2.5em;padding:.7em 0;color:#777;border-top:#BBB solid 1px;">' +
                'Powered by SickGear.</footer></body>',
                'html'))
        except (StandardError, Exception):
            try:
                msg = MIMEText(body)
            except (StandardError, Exception):
                msg = MIMEText('Episode %s' % title)

        msg['Subject'] = '%s%s: %s' % (lang, title, body)
        msg['From'] = sickbeard.EMAIL_FROM
        msg['To'] = ','.join(to)
        msg['Date'] = formatdate(localtime=True)
        if self._sendmail(sickbeard.EMAIL_HOST, sickbeard.EMAIL_PORT, sickbeard.EMAIL_FROM, sickbeard.EMAIL_TLS,
                          sickbeard.EMAIL_USER, sickbeard.EMAIL_PASSWORD, to, msg):
            self._log_debug(u'%s notification sent to [%s] for "%s"' % (title, to, body))
        else:
            self._log_error(u'%s notification ERROR: %s' % (title, self.last_err))

    def test_notify(self, host, port, smtp_from, use_tls, user, pwd, to):
        self._testing = True

        msg = MIMEText('Success.  This is a SickGear test message. Typically sent on, %s' % notify_strings['download'])
        msg['Subject'] = 'SickGear: Test message'
        msg['From'] = smtp_from
        msg['To'] = to
        msg['Date'] = formatdate(localtime=True)

        r = self._sendmail(host, port, smtp_from, use_tls, user, pwd, [to], msg, True)
        return self._choose(('Success, notification sent.',
                             'Failed to send notification: %s' % self.last_err)[not r], r)

    def notify_snatch(self, ep_name, title=None):
        """
        Send a notification that an episode was snatched

        :param ep_name: The name of the episode that was snatched
        :param title: The title of the notification (optional)
        """

        title = sickbeard.EMAIL_OLD_SUBJECTS and 'Snatched' or title or notify_strings['snatch']
        self._notify(title, ep_name)

    def notify_download(self, ep_name, title=None):
        """
        Send a notification that an episode was downloaded

        :param ep_name: The name of the episode that was downloaded
        :param title: The title of the notification (optional)
        """

        title = sickbeard.EMAIL_OLD_SUBJECTS and 'Downloaded' or title or notify_strings['download']
        self._notify(title, ep_name)

    def notify_subtitle_download(self, ep_name, lang, title=None):
        """
        Send a notification that a subtitle was downloaded

        :param ep_name: The name of the episode that was downloaded
        :param lang: Subtitle language
        :param title: The title of the notification (optional)
        """

        title = sickbeard.EMAIL_OLD_SUBJECTS and 'Subtitle Downloaded' or title or notify_strings['subtitle_download']
        self._notify(title, ep_name, '%s ' % lang, '</b></p>\n<p>Language: <b>%s' % lang)


notifier = EmailNotifier
