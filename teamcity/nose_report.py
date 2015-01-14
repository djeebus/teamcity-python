# coding=utf-8
import os
import sys
import datetime
import inspect

from teamcity import is_running_under_teamcity
from teamcity.common import is_string, split_output, limit_output, get_class_fullname, convert_error_to_string
from teamcity.messages import TeamcityServiceMessages

from nose.exc import SkipTest, DeprecatedTest


CONTEXT_SUITE_FQN = "nose.suite.ContextSuite"


# from nose.util.ln
def _ln(label):
    label_len = len(label) + 2
    chunk = (70 - label_len) // 2
    out = '%s %s %s' % ('-' * chunk, label, '-' * chunk)
    pad = 70 - len(out)
    if pad > 0:
        out = out + ('-' * pad)
    return out


_captured_output_start_marker = _ln('>> begin captured stdout <<') + "\n"
_captured_output_end_marker = "\n" + _ln('>> end captured stdout <<')

_real_stdout = sys.stdout


class TeamcityReport(object):
    name = 'teamcity-report'
    score = 10000

    def __init__(self):
        super(TeamcityReport, self).__init__()

        self.messages = TeamcityServiceMessages(_real_stdout)
        self.test_started_datetime_map = {}
        self.enabled = False

    def get_test_id(self, test):
        if is_string(test):
            return test

        # Handle special "tests"
        test_class_name = get_class_fullname(test)
        if test_class_name == CONTEXT_SUITE_FQN:
            if inspect.ismodule(test.context):
                module_name = test.context.__name__
                return module_name + "." + test.error_context

        # Force test_id for doctests
        real_test = getattr(test, "test", test)
        real_test_class_name = get_class_fullname(real_test)
        if real_test_class_name != "doctest.DocTestCase" and real_test_class_name != "nose.plugins.doctests.DocTestCase":
            desc = test.shortDescription()
            if desc and desc != test.id():
                return "%s (%s)" % (test.id(), desc)

        return test.id()

    def configure(self, options, conf):
        self.enabled = is_running_under_teamcity()

    def options(self, parser, env=os.environ):
        pass

    def report_fail(self, test, fail_type, err):
        # workaround nose bug on python 3
        if is_string(err[1]):
            err = (err[0], Exception(err[1]), err[2])

        test_id = self.get_test_id(test)

        details = convert_error_to_string(err)

        start_index = details.find(_captured_output_start_marker)
        end_index = details.find(_captured_output_end_marker)

        if 0 <= start_index < end_index:
            captured_output = details[start_index + len(_captured_output_start_marker):end_index]
            details = details[:start_index] + details[end_index + len(_captured_output_end_marker):]

            for chunk in split_output(limit_output(captured_output)):
                self.messages.testStdOut(test_id, chunk, flowId=test_id)

        self.messages.testFailed(test_id, message=fail_type, details=details, flowId=test_id)

    def addError(self, test, err):
        test_class_name = get_class_fullname(test)
        test_id = self.get_test_id(test)

        if issubclass(err[0], SkipTest):
            self.messages.testIgnored(test_id, message="Skipped", flowId=test_id)
        elif issubclass(err[0], DeprecatedTest):
            self.messages.testIgnored(test_id, message="Deprecated", flowId=test_id)
        elif test_class_name == CONTEXT_SUITE_FQN and test.error_context == "setup":
            self.messages.testStarted(test_id, captureStandardOutput='true', flowId=test_id)
            self.report_fail(test, 'setup error', err)
            self.messages.testFinished(test_id, flowId=test_id)
        else:
            self.report_fail(test, 'Error', err)

    def addFailure(self, test, err):
        self.report_fail(test, 'Failure', err)

    def startTest(self, test):
        test_id = self.get_test_id(test)

        self.test_started_datetime_map[test_id] = datetime.datetime.now()
        self.messages.testStarted(test_id, captureStandardOutput='true', flowId=test_id)

    def stopTest(self, test):
        test_id = self.get_test_id(test)

        time_diff = datetime.datetime.now() - self.test_started_datetime_map[test_id]
        self.messages.testFinished(test_id, testDuration=time_diff, flowId=test_id)
