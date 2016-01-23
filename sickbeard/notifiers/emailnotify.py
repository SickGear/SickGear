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

import re

import sickbeard
import smtplib

from sickbeard import db
from sickbeard import logger
from sickbeard.common import notifyStrings, NOTIFY_SNATCH, NOTIFY_DOWNLOAD, NOTIFY_SUBTITLE_DOWNLOAD

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate


class EmailNotifier:

    def __init__(self):

        self.last_err = None

    def test_notify(self, host, port, smtp_from, use_tls, user, pwd, to):

        msg = MIMEText('Success.  This is a SickGear test message. Typically sent on, %s' %
                       notifyStrings[NOTIFY_DOWNLOAD])
        msg['Subject'] = 'SickGear: Test message'
        msg['From'] = smtp_from
        msg['To'] = to
        msg['Date'] = formatdate(localtime=True)
        return self._sendmail(host, port, smtp_from, use_tls, user, pwd, [to], msg, True)

    def _send_email(self, title, ep_name, lang='', extra='', force=False):

        if not sickbeard.USE_EMAIL and not force:
            return

        show = ep_name.split(' - ')[0]
        to = self._get_recipients(show)
        if not any(to):
            logger.log(u'No email recipients to notify, skipping', logger.WARNING)
            return

        logger.log(u'Email recipients to notify: %s' % to, logger.DEBUG)

        try:
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(
                '<body style="font-family:Helvetica, Arial, sans-serif;">' +
                '<h3>SickGear Notification - %s</h3>\n' % title +
                '<p>Show: <b>' + show.encode('ascii', 'xmlcharrefreplace') +
                '</b></p>\n<p>Episode: <b>' +
                unicode(re.search('.+ - (.+?-.+) -.+', ep_name).group(1)).encode('ascii', 'xmlcharrefreplace') +
                extra +
                '</b></p>\n\n' +
                '<footer style="margin-top:2.5em;padding:.7em 0;color:#777;border-top:#BBB solid 1px;">' +
                'Powered by SickGear.</footer></body>',
                'html'))
        except:
            try:
                msg = MIMEText(ep_name)
            except:
                msg = MIMEText('Episode %s' % title)

        msg['Subject'] = '%s%s: %s' % (lang, title, ep_name)
        msg['From'] = sickbeard.EMAIL_FROM
        msg['To'] = ','.join(to)
        msg['Date'] = formatdate(localtime=True)
        if self._sendmail(sickbeard.EMAIL_HOST, sickbeard.EMAIL_PORT, sickbeard.EMAIL_FROM, sickbeard.EMAIL_TLS,
                          sickbeard.EMAIL_USER, sickbeard.EMAIL_PASSWORD, to, msg):
            logger.log(u'%s notification sent to [%s] for "%s"' % (title, to, ep_name), logger.DEBUG)
        else:
            logger.log(u'%s notification ERROR: %s' % (title, self.last_err), logger.ERROR)

    def notify_snatch(self, ep_name, title=notifyStrings[NOTIFY_SNATCH]):
        """
        Send a notification that an episode was snatched

        :param ep_name: The name of the episode that was snatched
        :param title: The title of the notification (optional)
        """

        if sickbeard.EMAIL_NOTIFY_ONSNATCH:
            title = sickbeard.EMAIL_OLD_SUBJECTS and 'Snatched' or title
            self._send_email(title, ep_name)

    def notify_download(self, ep_name, title=notifyStrings[NOTIFY_DOWNLOAD]):
        """
        Send a notification that an episode was downloaded

        :param ep_name: The name of the episode that was downloaded
        :param title: The title of the notification (optional)
        """

        if sickbeard.EMAIL_NOTIFY_ONDOWNLOAD:
            title = sickbeard.EMAIL_OLD_SUBJECTS and 'Downloaded' or title
            self._send_email(title, ep_name)

    def notify_subtitle_download(self, ep_name, lang, title=notifyStrings[NOTIFY_SUBTITLE_DOWNLOAD]):
        """
        Send a notification that a subtitle was downloaded

        :param ep_name: The name of the episode that was downloaded
        :param lang: Subtitle language
        :param title: The title of the notification (optional)
        """

        if sickbeard.EMAIL_NOTIFY_ONSUBTITLEDOWNLOAD:
            title = sickbeard.EMAIL_OLD_SUBJECTS and 'Subtitle Downloaded' or title
            self._send_email(title, ep_name, '%s ' % lang, '</b></p>\n<p>Language: <b>%s' % lang)

    def notify_git_update(self, new_version='??'):

        pass

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

    def _sendmail(self, host, port, smtp_from, use_tls, user, pwd, to, msg, smtp_debug=False):

        use_tls = 1 == sickbeard.helpers.tryInt(use_tls)
        login = any(user) and any(pwd)
        logger.log(u'Sendmail HOST: %s; PORT: %s; LOGIN: %s, TLS: %s, USER: %s, FROM: %s, TO: %s' % (
            host, port, login, use_tls, user, smtp_from, to), logger.DEBUG)

        try:
            srv = smtplib.SMTP(host, int(port))
            if smtp_debug:
                srv.set_debuglevel(1)

            if use_tls or login:
                srv.ehlo()
                logger.log(u'Sent initial EHLO command', logger.DEBUG)

                if use_tls:
                    srv.starttls()
                    srv.ehlo()
                    logger.log(u'Sent STARTTLS and EHLO command', logger.DEBUG)

                if login:
                    srv.login(user, pwd)
                    logger.log(u'Sent LOGIN command', logger.DEBUG)

            srv.sendmail(smtp_from, to, msg.as_string())
            srv.quit()

        except Exception as e:
            self.last_err = '%s' % e
            return False

        return True


notifier = EmailNotifier
