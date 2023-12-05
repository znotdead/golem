import json
import os
from types import SimpleNamespace

import pytest

from golem.test_runner import test_runner
from golem.test_runner.conf import ResultsEnum
from golem.execution_runner import execution_runner
from golem.gui import gui_utils
from golem.core import settings_manager
from golem.core import test as test_module
from golem.report import execution_report
from golem.report import test_report
from golem.core import utils


def _define_browsers_mock(selected_browsers):
    default_browsers = gui_utils.get_supported_browsers_suggestions()
    return execution_runner.define_browsers(selected_browsers, [], default_browsers, [])


def _mock_report_directory(project, execution_name, timestamp):
    return execution_report.create_execution_directory(project, execution_name, timestamp)


def _read_report_json(execdir, test_name, set_name=''):
    path = test_report.test_file_report_dir(test_name, execdir=execdir, set_name=set_name)
    path = os.path.join(path, 'report.json')
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="function")
def runfix(project_module, test_utils):
    """A fixture that
      Uses a project fix with module scope,
      Creates a random test
      Creates a report directory for a future execution
      Gets the settings and browser values required to run test
      Can run the test provided the test code
      Can read the json report
    """
    testdir, project = project_module.activate()
    test_name = test_utils.create_random_test(project)
    timestamp = utils.get_timestamp()
    exec_dir = _mock_report_directory(project, execution_name=test_name,
                                      timestamp=timestamp)
    settings = settings_manager.get_project_settings(project)
    browser = _define_browsers_mock(['chrome'])[0]
    env_name = None

    def set_content(test_content):
        test_module.edit_test_code(project, test_name, test_content)

    def run_test(code, test_data={}, secrets={}, from_suite=False, set_name=''):
        set_content(code)
        test_runner.run_test(testdir, project, test_name, test_data, secrets, browser,
                             env_name, settings, exec_dir, set_name=set_name,
                             test_functions=[], from_suite=from_suite)

    def read_report(set_name=''):
        return _read_report_json(exec_dir, test_name, set_name=set_name)

    fix = SimpleNamespace(testdir=testdir, project=project, test_name=test_name,
                          report_directory=exec_dir, settings=settings,
                          browser=browser, set_content=set_content,
                          run_test=run_test, read_report=read_report)
    return fix


SUCCESS_MESSAGE = 'Test Result: SUCCESS'
CODE_ERROR_MESSAGE = 'Test Result: CODE ERROR'
FAILURE_MESSAGE = 'Test Result: FAILURE'
ERROR_MESSAGE = 'Test Result: ERROR'


class TestRunTest:

    def test_import_error_on_test(self, runfix, caplog):
        """The test fails with 'code error' when it has a syntax error
        Test result is code error"""
        code = """
description = 'some description'

# missing colon
def test(data)
step('this step wont be run')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].levelname == 'ERROR'
        error_contains = 'def test(data)'
        error_contains_ver2 = "SyntaxError: expected ':'"
        assert error_contains in r[2].message and error_contains_ver2 in r[2].message
        report = runfix.read_report()
        assert len(report) == 1
        report = report[0]
        assert report['test_file'] == runfix.test_name
        # test functions were not read, 'setup' is a pseudo test
        assert report['test'] == 'setup'
        assert report['set_name'] == ''
        assert report['environment'] == ''
        assert report['result'] == ResultsEnum.CODE_ERROR
        assert report['description'] == ''  # description could not be read
        assert report['browser'] == ''
        assert report['test_data'] == {}
        assert report['steps'] == []
        assert len(report['errors']) == 1
        assert report['errors'][0]['message'] == "SyntaxError: expected ':'"
        assert (
            error_contains in report['errors'][0]['description']
            and error_contains_ver2 in report['errors'][0]['description']
        )
        assert report['result'] == ResultsEnum.CODE_ERROR
        assert report['set_name'] == ''
        assert report['steps'] == []
        assert report['test_file'] == runfix.test_name
        assert report['test_data'] == {}

    def test_import_error_page(self, runfix, caplog, test_utils):
        """The test fails with 'code error' when an imported page has a syntax error"""
        page_code = """
element1 = ('id', 'someId'
element2 = ('css', '.oh.no')
"""
        page_name = test_utils.create_random_page(runfix.project, code=page_code)
        code = f"""
pages = ['{page_name}']
def before_test(data):
    step('this step wont be run')
def test(data):
    step('this step wont be run')
def after_Test(data):
    step('this step wont be run')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].levelname == 'ERROR'
        error_contains_one = "SyntaxError: \'(\' was never closed\n"
        error_contains_two = "element1 = (\'id\', \'someId\'\n"
        assert error_contains_one in r[2].message and \
               error_contains_two in r[2].message
        r = runfix.read_report()
        assert len(r) == 1
        r = r[0]
        assert r['test_file'] == runfix.test_name
        assert r['test'] == 'setup'
        assert r['browser'] == ''
        assert r['description'] == ''  # description could not be read
        assert r['environment'] == ''
        assert len(r['errors']) == 1
        assert "SyntaxError: \'(\' was never closed\n" in r['errors'][0]['message']
        assert error_contains_one in r['errors'][0]['description'] and \
               error_contains_two in r['errors'][0]['description']
        assert r['result'] == ResultsEnum.CODE_ERROR
        assert r['set_name'] == ''
        assert r['steps'] == []
        assert r['test_data'] == {}
        assert 'elapsed_time' in r
        assert 'timestamp' in r
        assert len(r.keys()) == 12

    def test_single_function_success(self, runfix, caplog):
        """Test with only one test function runs successfully"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def test_one(data):
    step('test step')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == 'before_test step'
        assert r[3].message == 'Test started: test_one'
        assert r[4].message == 'test step'
        assert r[5].message == SUCCESS_MESSAGE
        assert r[6].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 1
        r = r[0]
        assert r['test_file'] == runfix.test_name
        assert r['test'] == 'test_one'
        assert r['browser'] == 'chrome'
        assert r['description'] == 'some description'
        assert r['environment'] == ''
        assert r['errors'] == []
        assert r['result'] == ResultsEnum.SUCCESS
        assert r['set_name'] == ''
        assert r['steps'] == [
            {'message': 'test step', 'screenshot': None, 'error': None},
        ]
        assert r['test_data'] == {}
        assert 'elapsed_time' in r
        assert 'timestamp' in r
        assert len(r.keys()) == 12

    def test_multi_function_success(self, runfix, caplog):
        """Test with two test functions runs successfully"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def test_one(data):
    step('test one step')

def test_two(data):
    step('test two step')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == 'before_test step'
        assert r[3].message == 'Test started: test_one'
        assert r[4].message == 'test one step'
        assert r[5].message == SUCCESS_MESSAGE
        assert r[6].message == 'Test started: test_two'
        assert r[7].message == 'test two step'
        assert r[8].message == SUCCESS_MESSAGE
        assert r[9].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test_file'] == runfix.test_name
        assert r[0]['test'] == 'test_one'
        assert r[0]['errors'] == []
        assert r[0]['result'] == ResultsEnum.SUCCESS
        assert r[0]['set_name'] == ''
        assert r[0]['steps'] == [{'message': 'test one step', 'screenshot': None, 'error': None}]
        assert r[1]['test_file'] == runfix.test_name
        assert r[1]['test'] == 'test_two'
        assert r[1]['errors'] == []
        assert r[1]['result'] == ResultsEnum.SUCCESS
        assert r[1]['set_name'] == ''
        assert r[1]['steps'] == [{'message': 'test two step', 'screenshot': None, 'error': None}]

    def test_first_test_passes_second_test_fails(self, runfix, caplog):
        """Test with two test functions, first passes, second fails"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def test_one(data):
    step('test one step')

def test_two(data):
    assert False

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == 'before_test step'
        assert r[3].message == 'Test started: test_one'
        assert r[4].message == 'test one step'
        assert r[5].message == SUCCESS_MESSAGE or r[5].message == FAILURE_MESSAGE
        assert r[6].message == 'Test started: test_two'
        assert 'AssertionError' in r[7].message
        assert r[8].message == FAILURE_MESSAGE or r[5].message == SUCCESS_MESSAGE
        assert r[9].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test_file'] == runfix.test_name
        assert r[0]['test'] == 'test_one'
        assert r[0]['errors'] == []
        assert r[0]['steps'] == [
            {'message': 'test one step', 'screenshot': None, 'error': None},
        ]
        assert r[1]['test_file'] == runfix.test_name
        assert r[1]['test'] == 'test_two'
        assert len(r[1]['errors']) == 1
        assert r[1]['errors'][0]['message'] == 'AssertionError: '
        assert r[1]['result'] == ResultsEnum.FAILURE
        assert len(r[1]['steps']) == 1
        assert r[1]['steps'][0]['message'] == 'Failure'

    def test_first_test_fails_second_test_fails(self, runfix, caplog):
        """Test with two test functions, both fail"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def test_one(data):
    assert 2 + 2 == 5

def test_two(data):
    assert False

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == 'before_test step'
        assert r[3].message == 'Test started: test_one'
        assert 'AssertionError' in r[4].message
        assert r[5].message == FAILURE_MESSAGE
        assert r[6].message == 'Test started: test_two'
        assert 'AssertionError' in r[7].message
        assert r[8].message == FAILURE_MESSAGE
        assert r[9].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test_file'] == r[1]['test_file'] == runfix.test_name
        assert r[0]['result'] == r[1]['result'] == ResultsEnum.FAILURE
        assert r[0]['steps'][0]['message'] == r[1]['steps'][0]['message'] == 'Failure'
        assert len(r[0]['steps']) == len(r[1]['steps']) == 1
        assert len(r[0]['errors']) == len(r[1]['errors']) == 1
        assert r[0]['test'] == 'test_one'
        assert r[0]['errors'][0]['message'] == 'AssertionError: '
        assert r[1]['test'] == 'test_two'
        assert r[1]['errors'][0]['message'] == 'AssertionError: '

    def test_file_has_no_test_functions(self, runfix, caplog):
        """Test does not have any function starting with 'test'"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def this_is_not_a_test(data):
    step('test step')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == f'No tests were found for file: {runfix.test_name}'
        assert len(r) == 3
        # assert report json was not generated

    @pytest.mark.slow
    def test_success_with_data(self, runfix, caplog):
        """Test runs successfully with test data"""
        code = """
description = 'some description'

def before_test(data):
    step('before_test step')

def test_name(data):
    step('test step')

def after_test(data):
    step('after_test step')
"""
        test_data = {
            'username': 'username1',
            'password': 'password1'
        }
        secrets = dict(very='secret')
        runfix.run_test(code, test_data=test_data, secrets=secrets)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].message == 'Using data:\n    username: username1\n    password: password1'
        assert r[3].message == 'before_test step'
        assert r[4].message == 'Test started: test_name'
        assert r[5].message == 'test step'
        assert r[6].message == SUCCESS_MESSAGE
        assert r[7].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 1
        r = r[0]
        assert r['test_file'] == runfix.test_name
        assert r['test'] == 'test_name'
        assert r['browser'] == 'chrome'
        assert r['description'] == 'some description'
        assert r['environment'] == ''
        assert r['errors'] == []
        assert r['result'] == ResultsEnum.SUCCESS
        assert r['set_name'] == ''  # set_name is empty because it only has one set of data
        assert r['steps'] == [
            {'message': 'test step', 'screenshot': None, 'error': None},
        ]
        assert r['test_data'] == {'username': "'username1'", 'password': "'password1'"}
        assert 'elapsed_time' in r
        assert 'timestamp' in r
        assert len(r.keys()) == 12

    def test_assertion_failure_in_before_test(self, runfix, caplog):
        """The test ends with 'failure' when the before_test function throws AssertionError.
        Tests are not run
        after_test is run
        """
        code = """
description = 'desc'

def before_test(data):
    fail('before_test step fail')

def test_one(data):
    step('test step')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].levelname == 'ERROR'
        assert 'before_test step fail' in r[2].message
        assert 'AssertionError: before_test step fail' in r[2].message
        assert r[3].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 1
        r = r[0]
        assert r['test_file'] == runfix.test_name
        assert r['test'] == 'before_test'
        assert r['description'] == 'desc'
        assert len(r['errors']) == 1
        assert 'before_test step fail' in r['errors'][0]['message']
        assert r['result'] == ResultsEnum.FAILURE

    @pytest.mark.slow
    def test_failure_and_error_in_before_test(self, runfix, caplog):
        """The test ends with 'failure' when the before_test function throws AssertionError,
        even when there's an error in before_test
        Test is not run
        after_test is run
        """
        code = """
description = 'desc'

def before_test(data):
    error('error in before_test')
    fail('before_test step fail')

def test_one(data):
    step('test step')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = runfix.read_report()
        r = r[0]
        assert len(r['errors']) == 2
        assert r['result'] == ResultsEnum.FAILURE
        assert r['errors'][0]['message'] == 'error in before_test'
        assert r['errors'][1]['message'] == 'AssertionError: before_test step fail'

    # A5
    def test_failure_in_before_test_error_in_after_test(self, runfix, caplog):
        """before_test throws AssertionError
        after_test throws error
        tests are not run
        """
        code = """
description = 'desc'

def before_test(data):
    fail('before_test step fail')

def test_one(data):
    step('test step')

def after_test(data):
    step('after_test step')
    error('error in after_test')
"""
        runfix.run_test(code)
        r = caplog.records
        assert 'AssertionError: before_test step fail' in r[2].message
        assert r[3].message == 'after_test step'
        assert r[4].message == 'error in after_test'
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'before_test'
        assert len(r[0]['errors']) == 1
        assert r[0]['result'] == ResultsEnum.FAILURE
        assert r[0]['errors'][0]['message'] == 'AssertionError: before_test step fail'
        assert r[1]['test'] == 'after_test'
        assert len(r[1]['errors']) == 1
        assert r[1]['result'] == ResultsEnum.ERROR
        assert r[1]['errors'][0]['message'] == 'error in after_test'

    @pytest.mark.slow
    def test_failure_in_before_test_exception_in_after_test(self, runfix, caplog):
        """before_test throws AssertionError
        after_test throws AssertionError
        Test ends with 'failure'
        tests are not run
        """
        code = """
description = 'desc'

def before_test(data):
    fail('before_test step fail')

def test_one(data):
    step('test step')

def after_test(data):
    step('after_test step')
    foo = bar
"""
        runfix.run_test(code)
        r = caplog.records
        assert 'AssertionError: before_test step fail' in r[2].message
        assert r[3].message == 'after_test step'
        assert "NameError: name 'bar' is not defined" in r[4].message
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'before_test'
        assert r[0]['result'] == ResultsEnum.FAILURE
        assert len(r[0]['steps']) == 1
        assert len(r[0]['errors']) == 1
        assert r[0]['errors'][0]['message'] == 'AssertionError: before_test step fail'
        assert r[1]['test'] == 'after_test'
        assert r[1]['result'] == ResultsEnum.CODE_ERROR
        assert len(r[1]['steps']) == 2
        assert len(r[1]['errors']) == 1
        assert r[1]['errors'][0]['message'] == "NameError: name 'bar' is not defined"

    @pytest.mark.slow
    def test_failure_in_before_test_failure_in_after_test(self, runfix, caplog):
        """before_test throws AssertionError
        after_test throws exception
        Test ends with 'failure'
        tests are not run
        """
        code = """
description = 'desc'

def before_test(data):
    fail('before_test step fail')

def test(data):
    step('test step')

def after_test(data):
    fail('failure in after_test')
"""
        runfix.run_test(code)
        r = caplog.records
        assert 'before_test step fail' in r[2].message
        assert 'AssertionError: failure in after_test' in r[3].message
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'before_test'
        assert r[0]['result'] == ResultsEnum.FAILURE
        assert r[1]['test'] == 'after_test'
        assert r[1]['result'] == ResultsEnum.FAILURE

#     def test_run_test__exception_in_setup(self, runfix, caplog):
#         """Setup throws exception
#         Test ends with 'code error'
#         test() is not run
#         teardown() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     foo = bar
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     step('teardown step')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[4].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert len(report['errors']) == 1
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 2
#         assert report['errors'][0]['message'] == "NameError: name 'bar' is not defined"

#     def test_run_test__exception_and_error_in_setup(self, runfix, caplog):
#         """Setup has error and throws exception
#         Test ends with 'code error'
#         test() is not run
#         teardown() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     error('setup error')
#     foo = bar
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     step('teardown step')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == 'setup error'
#         assert report['errors'][1]['message'] == "NameError: name 'bar' is not defined"

#     def test_run_test__exception_in_setup_exception_in_teardown(self, runfix, caplog):
#         """Setup throws exception
#         Teardown throws exception
#         Test ends with 'code error'
#         test() is not run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     foo = bar
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     foo = baz
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[4].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 2
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == "NameError: name 'bar' is not defined"
#         assert report['errors'][1]['message'] == "NameError: name 'baz' is not defined"

#     def test_run_test__exception_in_setup_failure_in_teardown(self, runfix, caplog):
#         """Setup throws exception
#         Teardown throws AssertionError
#         Test ends with 'code error'
#         test() is not run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     foo = bar
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     fail('teardown failure')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[4].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 2
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == "NameError: name 'bar' is not defined"
#         assert report['errors'][1]['message'] == 'AssertionError: teardown failure'

#     def test_run_test__error_in_setup(self, runfix, caplog):
#         """Setup has error
#         test() is run
#         teardown() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     error('setup error')
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     step('teardown step')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.ERROR
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 1
#         assert report['errors'][0]['message'] == "setup error"

#     def test_run_test__error_in_setup_exception_in_teardown(self, runfix, caplog):
#         """Setup has error
#         Teardown throws exception
#         test() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     error('setup error')
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     foo = bar
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == 'setup error'
#         assert report['errors'][1]['message'] == "NameError: name 'bar' is not defined"

#     def test_run_test__error_in_setup_failure_in_teardown(self, runfix, caplog):
#         """Setup has error
#         Teardown throws AssertionError
#         test() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     error('setup error')
#
# def test(data):
#     step('test step')
#
# def teardown(data):
#     fail('teardown fail')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == FAILURE_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.FAILURE
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == 'setup error'
#         assert report['errors'][1]['message'] == 'AssertionError: teardown fail'

    def test_failure_in_test(self, runfix, caplog):
        """a test throws AssertionError
        after_test() is run
        """
        code = """
description = 'desc'

def before_test(data):
    step('before_test step')

def test(data):
    step('test step')
    fail('test fail')

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[3].message == 'Test started: test'
        assert r[4].message == 'test step'
        assert 'AssertionError: test fail' in r[5].message
        assert r[6].message == FAILURE_MESSAGE
        assert r[7].message == 'after_test step'
        report = runfix.read_report()
        assert len(report) == 1
        r = report[0]
        assert r['result'] == ResultsEnum.FAILURE
        assert len(r['steps']) == 2
        assert len(r['errors']) == 1
        assert r['errors'][0]['message'] == 'AssertionError: test fail'

#     def test_run_test__failure_and_error_in_test(self, runfix, caplog):
#         """test() has error and throws AssertionError
#         teardown() is run
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     step('setup step')
#
# def test(data):
#     error('test error')
#     fail('test fail')
#
# def teardown(data):
#     step('teardown step')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[6].message == FAILURE_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.FAILURE
#         assert len(report['steps']) == 4
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == 'test error'
#         assert report['errors'][1]['message'] == 'AssertionError: test fail'

    def test_failure_in_test_exception_in_after_test(self, runfix, caplog):
        """test() throws AssertionError
        after_test() throws exception
        """
        code = """
description = 'desc'

def before_test(data):
    step('before_test step')

def test_one(data):
    fail('test fail')

def after_test(data):
    foo = bar
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[2].message == 'before_test step'
        assert r[3].message == 'Test started: test_one'
        assert 'AssertionError: test fail' in r[4].message
        assert r[5].message == FAILURE_MESSAGE
        assert "NameError: name 'bar' is not defined" in r[6].message
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'test_one'
        assert r[0]['result'] == ResultsEnum.FAILURE
        assert len(r[0]['steps']) == 1
        assert len(r[0]['errors']) == 1
        assert r[0]['errors'][0]['message'] == 'AssertionError: test fail'
        assert r[1]['test'] == 'after_test'
        assert r[1]['result'] == ResultsEnum.CODE_ERROR
        assert len(r[1]['errors']) == 1
        assert r[1]['errors'][0]['message'] == "NameError: name 'bar' is not defined"

#     def test_run_test__failure_in_test_failure_in_teardown(self, runfix, caplog):
#         """test() throws AssertionError
#         teardown() throws AssertionError
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     step('setup step')
#
# def test(data):
#     fail('test fail')
#
# def teardown(data):
#     fail('teardown fail')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == FAILURE_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.FAILURE
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == 'AssertionError: test fail'
#         assert report['errors'][1]['message'] == 'AssertionError: teardown fail'

#     def test_exception_in_test(self, runfix, caplog):
#         """test() throws exception"""
#         code = """
# description = 'desc'
#
# def setup(data):
#     step('setup step')
#
# def test(data):
#     foo = bar
#
# def teardown(data):
#     step('teardown step')
# """
#         runfix.run_test(code)
#         r = caplog.records
#         assert r[5].message == CODE_ERROR_MESSAGE
#         r = runfix.read_report()
#         assert r['result'] == ResultsEnum.CODE_ERROR
#         assert len(r['steps']) == 3
#         assert len(r['errors']) == 1
#         assert r['errors'][0]['message'] == "NameError: name 'bar' is not defined"

    def test_error_and_exception_in_test(self, runfix, caplog):
        """test() throws error and AssertionError"""
        code = """
description = 'desc'

def before_test(data):
    step('before_test step')

def test(data):
    error('error in test')
    foo = bar

def after_test(data):
    step('after_test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[4].message == 'error in test'
        assert "NameError: name 'bar' is not defined" in r[5].message
        assert r[6].message == CODE_ERROR_MESSAGE
        r = runfix.read_report()
        r = r[0]
        assert r['result'] == ResultsEnum.CODE_ERROR
        assert len(r['steps']) == 2
        assert len(r['errors']) == 2
        assert r['errors'][0]['message'] == 'error in test'
        assert r['errors'][1]['message'] == "NameError: name 'bar' is not defined"

#     def test_exception_in_test_failure_in_teardown(self, runfix, caplog):
#         """test() throws exception
#         teardown() throws AssertionError
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     step('setup step')
#
# def test(data):
#     foo = bar
#
# def teardown(data):
#     fail('teardown fail')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == CODE_ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.CODE_ERROR
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 2
#         assert report['errors'][0]['message'] == "NameError: name 'bar' is not defined"
#         assert report['errors'][1]['message'] == 'AssertionError: teardown fail'

#     def test_error_in_setup_test_and_teardown(self, runfix, caplog):
#         """setup(), test() and teardown() have errors
#         """
#         code = """
# description = 'desc'
#
# def setup(data):
#     error('setup error')
#
# def test(data):
#     error('test error')
#
# def teardown(data):
#     error('teardown error')
# """
#         runfix.run_test(code)
#         records = caplog.records
#         assert records[5].message == ERROR_MESSAGE
#         report = runfix.read_report()
#         assert report['result'] == ResultsEnum.ERROR
#         assert len(report['steps']) == 3
#         assert len(report['errors']) == 3
#         assert report['errors'][0]['message'] == 'setup error'
#         assert report['errors'][1]['message'] == 'test error'
#         assert report['errors'][2]['message'] == 'teardown error'

    # def test_run_test__skip_true__not_from_suite(self, runfix, caplog):
    #     code = ('skip = True\n'
    #             'def setup(data):\n'
    #             '    step("setup")\n'
    #             'def test(data):\n'
    #             '    step("test")\n'
    #             'def teardown(data):\n'
    #             '    step("teardown")')
    #     runfix.run_test(code, from_suite=False)
    #     records = caplog.records
    #     assert records[2].message == 'setup'
    #     assert records[3].message == 'test'
    #     assert records[4].message == 'teardown'
    #     assert records[5].message == SUCCESS_MESSAGE
    #     report = runfix.read_report()
    #     assert report['result'] == ResultsEnum.SUCCESS

    def test_run_test__skip_true__from_suite(self, runfix, caplog):
        """Test functions are skipped when run from suite and skip is True"""
        code = ('skip = True\n'
                'def before_test(data):\n'
                '    step("before_test")\n'
                'def test(data):\n'
                '    step("test")\n'
                'def after_test(data):\n'
                '    step("after_test")')
        runfix.run_test(code, from_suite=True)
        records = caplog.records
        assert records[2].message == 'Test skipped: test'
        report = runfix.read_report()
        assert len(report) == 1
        assert report[0]['result'] == ResultsEnum.SKIPPED
    #
    # # S1
    # def test_run_test__skip_true__syntax_error(self, runfix, caplog):
    #     """when test with skip=True has an error on import the test
    #     ends with code error
    #     """
    #     code = ('skip = True\n'
    #             'def test(data)\n'
    #             '    step("test")\n')
    #     runfix.run_test(code, from_suite=True)
    #     records = caplog.records
    #     assert records[2].levelname == 'ERROR'
    #     assert records[3].message == CODE_ERROR_MESSAGE
    #     report = runfix.read_report()
    #     assert len(report['errors']) == 1
    #     assert report['errors'][0]['message'] == 'SyntaxError: invalid syntax'
    #     assert report['result'] == ResultsEnum.CODE_ERROR

    def test_setup_is_deprecated(self, runfix, caplog):
        """setup test hook is run when before_test is not defined
        a deprecation warning log is displayed
        """
        code = """
def setup(data):
    fail('setup step fail')

def test_one(data):
    step('test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[0].message == f'Test execution started: {runfix.test_name}'
        assert r[1].message == 'Browser: chrome'
        assert r[2].levelname == 'INFO'
        assert r[2].message == 'setup hook function is deprecated, use before_test'
        assert r[3].levelname == 'ERROR'
        assert 'setup step fail' in r[3].message
        r = runfix.read_report()
        assert len(r) == 1
        r = r[0]
        assert r['test_file'] == runfix.test_name
        assert r['test'] == 'setup'
        assert len(r['errors']) == 1
        assert 'setup step fail' in r['errors'][0]['message']
        assert r['result'] == ResultsEnum.FAILURE

    def test_teardown_is_deprecated(self, runfix, caplog):
        """teardown test hook is run when after_test is not defined
        a deprecation warning log is displayed
        """
        code = """
def test_one(data):
    step('test step')

def teardown(data):
    fail('teardown fail')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[5].message == 'teardown hook function is deprecated, use after_test'
        assert 'AssertionError: teardown fail' in r[6].message
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'test_one'
        assert r[0]['result'] == ResultsEnum.SUCCESS
        assert r[1]['test'] == 'teardown'
        assert r[1]['result'] == ResultsEnum.FAILURE

    def test_before_each_hook(self, runfix, caplog):
        code = """
def before_each(data):
    step('before_each step')

def test_one(data):
    step('test step')

def test_two(data):
    step('test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[2].message == 'before_each step'
        assert r[3].message == 'Test started: test_one'
        assert r[4].message == 'test step'
        assert r[5].message == SUCCESS_MESSAGE
        assert r[6].message == 'before_each step'
        assert r[7].message == 'Test started: test_two'
        assert r[8].message == 'test step'
        assert r[9].message == SUCCESS_MESSAGE
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'test_one'
        assert r[0]['result'] == ResultsEnum.SUCCESS
        assert r[1]['test'] == 'test_two'
        assert r[1]['result'] == ResultsEnum.SUCCESS

    def test_after_each_hook(self, runfix, caplog):
        code = """
def after_each(data):
    step('after_each step')

def test_one(data):
    step('test step')

def test_two(data):
    step('test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[2].message == 'Test started: test_one'
        assert r[3].message == 'test step'
        assert r[4].message == SUCCESS_MESSAGE
        assert r[5].message == 'after_each step'
        assert r[6].message == 'Test started: test_two'
        assert r[7].message == 'test step'
        assert r[8].message == SUCCESS_MESSAGE
        assert r[9].message == 'after_each step'
        r = runfix.read_report()
        assert len(r) == 2
        assert r[0]['test'] == 'test_one'
        assert r[0]['result'] == ResultsEnum.SUCCESS
        assert r[1]['test'] == 'test_two'
        assert r[1]['result'] == ResultsEnum.SUCCESS

    def test_before_each_hook_fails(self, runfix, caplog):
        """When before_each hook fails, a report for it is generated.
        after_each for that test is not run.
        all subsequent tests are skipped. after_test is executed anyway"""
        code = """
def before_each(data):
    step('before_each step')
    fail('before_each fail')

def after_each(data):
    step('after_each step')

def after_test(data):
    step('after_test step')

def test_one(data):
    step('test step')

def test_two(data):
    step('test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[2].message == 'before_each step'
        assert 'AssertionError: before_each fail' in r[3].message
        assert r[4].message == 'Test skipped: test_one'
        assert r[5].message == 'Test skipped: test_two'
        assert r[6].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 3
        assert r[0]['test'] == 'before_each'
        assert r[0]['result'] == ResultsEnum.FAILURE
        assert r[1]['test'] == 'test_one'
        assert r[1]['result'] == ResultsEnum.SKIPPED
        assert r[2]['test'] == 'test_two'
        assert r[2]['result'] == ResultsEnum.SKIPPED

    def test_after_each_hook_fails(self, runfix, caplog):
        """When after_each hook fails, a report for it is generated.
        all subsequent tests are skipped. after_test is executed anyway"""
        code = """
def after_each(data):
    step('after_each step')
    fail('after_each fail')

def after_test(data):
    step('after_test step')

def test_one(data):
    step('test step')

def test_two(data):
    step('test step')
"""
        runfix.run_test(code)
        r = caplog.records
        assert r[2].message == 'Test started: test_one'
        assert r[3].message == 'test step'
        assert r[4].message == SUCCESS_MESSAGE
        assert r[5].message == 'after_each step'
        assert 'AssertionError: after_each fail' in r[6].message
        assert r[7].message == 'Test skipped: test_two'
        assert r[8].message == 'after_test step'
        r = runfix.read_report()
        assert len(r) == 3
        assert r[0]['test'] == 'test_one'
        assert r[0]['result'] == ResultsEnum.SUCCESS
        assert r[1]['test'] == 'after_each'
        assert r[1]['result'] == ResultsEnum.FAILURE
        assert r[2]['test'] == 'test_two'
        assert r[2]['result'] == ResultsEnum.SKIPPED


class TestTestRunnerSetExecutionModuleValues:

    def test_set_execution_module_runner_values(self, project_module, test_utils):
        testdir, project = project_module.activate()
        test_file = test_utils.create_random_test(project)
        test = test_module.Test(project, test_file)
        timestamp = utils.get_timestamp()
        executiondir = _mock_report_directory(project, test_file, timestamp)
        testfile_reportdir = test_report.test_file_report_dir(test_file, execdir=executiondir)
        assert testfile_reportdir
        settings = settings_manager.get_project_settings(project)
        browser = _define_browsers_mock(['chrome'])[0]
        test_data = {}
        secrets = {}
        env_name = 'foo'
        runner = test_runner.TestRunner(testdir, project, test_file, test_data, secrets,
                                        browser, env_name, settings, executiondir,
                                        set_name='')
        runner._set_execution_module_values()
        from golem import execution
        attrs = [x for x in dir(execution) if not x.startswith('_')]
        assert len(attrs) == 23
        assert execution.browser is None
        assert execution.browser_definition == browser
        assert execution.browsers == {}
        assert execution.data == {}
        assert execution.secrets == {}
        assert execution.description is None
        assert execution.settings == settings
        assert execution.test_file == test_file
        assert execution.test_dirname == test.dirname
        assert execution.test_path == test.path
        assert execution.project_name == project
        assert execution.project_path == test.project.path
        assert execution.testdir == testdir
        assert execution.execution_reportdir == executiondir
        assert execution.testfile_reportdir is None  # Not populated at this point
        assert execution.logger is None
        assert execution.tags == []
        assert execution.environment == env_name

        assert execution.test_name is None
        assert execution.steps == []
        assert execution.errors == []
        assert execution.test_reportdir is None
        assert execution.timers == {}

        # test _reset_execution_module_values_for_test_function
        execution.test_name = 'foo'
        execution.steps = ['foo']
        execution.errors = ['foo']
        execution.report_directory = 'foo'
        execution.timers = {'foo': 'bar'}

        runner._reset_execution_module_values_for_test_function(test_reportdir='x',
                                                                test_name='test-name')
        assert execution.test_name == 'test-name'
        assert execution.steps == []
        assert execution.errors == []
        assert execution.test_reportdir == 'x'
        assert execution.timers == {}
