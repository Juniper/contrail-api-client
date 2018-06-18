import os
import shutil
import tempfile

from testtools import TestCase

from vnc_api.vnc_api import CurlLogger, DEFAULT_LOG_DIR

class TestCurlLogger(TestCase):
    def test_absolute_logfile(self):
        tmp_dir = tempfile.mkdtemp()
        logfile = os.path.join(tmp_dir, 'vnc-api.log')
        log = CurlLogger(log_file=logfile)
        log.curl_logger.debug("Test absolute log file")
        self.assertTrue(os.path.exists(logfile))

    def test_logfile_when_etc_contrail_not_present(self):
        logfile = 'vnc-api.log'
        log = CurlLogger(log_file=logfile)
        log.curl_logger.debug("Test log file")
        self.assertTrue(os.path.exists(os.path.join(DEFAULT_LOG_DIR, logfile)))
        shutil.rmtree(DEFAULT_LOG_DIR)
# end class TestCurlLogger
