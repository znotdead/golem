"""Functions to interact with a webdriver browser object."""
import traceback
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from golem.core import utils
from golem.core.project import Project
from golem import execution
from selenium.webdriver.chrome.service import Service as ChromeService
from golem.webdriver import (
    GolemChromeDriver,
    GolemEdgeDriver,
    GolemGeckoDriver,
    GolemIeDriver,
    GolemRemoteDriver,
)


class InvalidBrowserIdError(Exception):
    pass


def element(*args, **kwargs):
    """Shortcut to golem.browser.get_browser().find()"""
    webelement = get_browser().find(*args, **kwargs)
    return webelement


def elements(*args, **kwargs):
    """Shortcut to golem.browser.get_browser().find_all()"""
    webelement = get_browser().find_all(*args, **kwargs)
    return webelement


def open_browser(browser_name=None, capabilities=None, remote_url=None, browser_id=None):
    """Open a browser.

    When no arguments are provided the browser is selected from
    the CLI -b|--browsers argument, the suite `browsers` list,
    or the `default_browser` setting.

    This can be overridden in two ways:
    - a local webdriver instance or
    - a remote Selenium Grid driver instance.

    To open a local Webdriver instance pass browser_name with a valid value:
    chrome, chrome-remote, chrome-headless, chrome-remote-headless, edge,
    edge-remote, firefox, firefox-headless, firefox-remote,
    firefox-remote-headless, ie, ie-remote, opera, opera-remote

    To open a remote Selenium Grid driver pass a capabilities dictionary and
    a remote_url.
    The minimum capabilities required is: {
        browserName: 'chrome'
        version: ''
        platform: ''
    }
    More info here: https://github.com/SeleniumHQ/selenium/wiki/DesiredCapabilities
    If remote_url is None it will be taken from the `remote_url` setting.

    When opening more than one browser instance per test
    provide a browser_id to switch between browsers later on

    :Raises:
      - InvalidBrowserIdError: The browser Id is already in use

    :Returns:
      the opened browser
    """
    @contextmanager
    def validate_exec_path(browser_name, exec_path_setting, settings):
        executable_path = settings[exec_path_setting]
        if executable_path:
            matched_executable_path = utils.match_latest_executable_path(executable_path,
                                                                         execution.testdir)
            if matched_executable_path:
                try:
                    yield matched_executable_path
                except Exception:
                    msg = (
                        f"Could not start {browser_name} driver using ",
                        f"the path '{executable_path}'\n",
                        f"verify that the {exec_path_setting} setting points ",
                        "to a valid webdriver executable.",
                    )
                    execution.logger.error(msg)
                    execution.logger.info(traceback.format_exc())
                    raise Exception(msg)
            else:
                msg = f'No executable file found using path {executable_path}'
                execution.logger.error(msg)
                raise Exception(msg)
        else:
            msg = f'{exec_path_setting} setting is not defined'
            execution.logger.error(msg)
            raise Exception(msg)

    @contextmanager
    def validate_remote_url(remote_url):
        if remote_url:
            yield remote_url
        else:
            msg = 'remote_url setting is required'
            execution.logger.error(msg)
            raise Exception(msg)

    project = Project(execution.project_name)
    browser_definition = execution.browser_definition
    settings = execution.settings
    if browser_name is None:
        browser_name = browser_definition['name']
    if capabilities is None:
        capabilities = browser_definition['capabilities']
    if remote_url is None:
        remote_url = settings['remote_url']
    is_custom = False

    if not browser_id:
        if len(execution.browsers) == 0:
            browser_id = 'main'
        else:
            browser_id = f'browser{len(execution.browsers)}'
    if browser_id in execution.browsers:
        raise InvalidBrowserIdError(f"browser id '{browser_id}' is already in use")

    # remote
    if capabilities:
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=capabilities)
    # Chrome
    elif browser_name == 'chrome':
        with validate_exec_path('chrome', 'chromedriver_path', settings) as ex_path:
            chrome_options = webdriver.ChromeOptions()
            if settings['start_maximized']:
                chrome_options.add_argument('start-maximized')
            service = ChromeService(executable_path=ex_path)
            driver = GolemChromeDriver(service=service, options=chrome_options)
    # Chrome headless
    elif browser_name == 'chrome-headless':
        with validate_exec_path('chrome', 'chromedriver_path', settings) as ex_path:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('headless')
            chrome_options.add_argument('--window-size=1600,1600')
            service = ChromeService(executable_path=ex_path)
            driver = GolemChromeDriver(service=service, options=chrome_options)
    # Chrome remote
    elif browser_name == 'chrome-remote':
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=DesiredCapabilities.CHROME)
    # Chrome remote headless
    elif browser_name == 'chrome-remote-headless':
        with validate_remote_url(remote_url) as remote_url:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('headless')
            desired_capabilities = chrome_options.to_capabilities()
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=desired_capabilities)
    # Edge
    elif browser_name == 'edge':
        with validate_exec_path('edge', 'edgedriver_path', settings) as ex_path:
            driver = GolemEdgeDriver(executable_path=ex_path)
    # Edge remote
    elif browser_name == 'edge-remote':
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=DesiredCapabilities.EDGE)
    # Firefox
    elif browser_name == 'firefox':
        with validate_exec_path('firefox', 'geckodriver_path', settings) as ex_path:
            driver = GolemGeckoDriver(executable_path=ex_path)
    # Firefox headless
    elif browser_name == 'firefox-headless':
        with validate_exec_path('firefox', 'geckodriver_path', settings) as ex_path:
            firefox_options = webdriver.FirefoxOptions()
            firefox_options.headless = True
            driver = GolemGeckoDriver(executable_path=ex_path, firefox_options=firefox_options)
    # Firefox remote
    elif browser_name == 'firefox-remote':
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=DesiredCapabilities.FIREFOX)
    # Firefox remote headless
    elif browser_name == 'firefox-remote-headless':
        with validate_remote_url(remote_url) as remote_url:
            firefox_options = webdriver.FirefoxOptions()
            firefox_options.headless = True
            desired_capabilities = firefox_options.to_capabilities()
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=desired_capabilities)
    # IE
    elif browser_name == 'ie':
        with validate_exec_path('internet explorer', 'iedriver_path', settings) as ex_path:
            driver = GolemIeDriver(executable_path=ex_path)
    # IE remote
    elif browser_name == 'ie-remote':
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=DesiredCapabilities.INTERNETEXPLORER)
    # Opera remote
    elif browser_name == 'opera-remote':
        with validate_remote_url(remote_url) as remote_url:
            driver = GolemRemoteDriver(command_executor=remote_url,
                                       desired_capabilities=DesiredCapabilities.OPERA)
    elif browser_name in project.custom_browsers():
        is_custom = True
        module, _ = project.custom_browser_module()
        custom_browser_func = getattr(module, browser_name)
        driver = custom_browser_func(settings)
    else:
        raise Exception(f"Error: {browser_definition['name']} is not a valid driver")

    if settings['start_maximized'] and not is_custom:
        # currently there is no way to maximize chrome window on OSX (chromedriver 2.43),
        # adding workaround
        # https://bugs.chromium.org/p/chromedriver/issues/detail?id=2389
        # https://bugs.chromium.org/p/chromedriver/issues/detail?id=2522
        # TODO: assess if this work-around is still needed when chromedriver 2.44 is released
        is_mac = 'mac' in driver.capabilities.get('platform', '').lower()
        if not ('chrome' in browser_definition['name'] and is_mac):
            driver.maximize_window()

    execution.browsers[browser_id] = driver
    # Set the new browser as the active browser
    execution.browser = driver
    return execution.browser


def get_browser() -> GolemRemoteDriver:
    """Returns the active browser. Starts a new one if there is none."""
    if not execution.browser:
        open_browser()
    return execution.browser


def activate_browser(browser_id):
    """Activate a browser.
    Only needed when the test starts more than one browser instance.

    :Raises:
      - InvalidBrowserIdError: The browser Id does not correspond to an opened browser

    :Returns:
      the active browser
    """
    if browser_id not in execution.browsers:
        raise InvalidBrowserIdError("'{}' is not a valid browser id. Current browsers are: {}"
                                    .format(browser_id, ', '.join(execution.browsers.keys())))
    else:
        execution.browser = execution.browsers[browser_id]
    return execution.browser
