# AppiumProxy
Python proxy to forward Appium session requests to different Appium server instances (so clients configure a single endpoint)

Introduction
------------

At the moment [Appium](http://appium.io/) only supports one session at a time. I.e. if you have serveral devices connected you can't run test on them simoultaneously using the same server instance.

A workaround to this is to start several appium servers on different ports and make your tests refer to these different instances. However, depending on how your testing project is set up, it can be cumbersome to have to configure different endpoints.

Then is when this simple tool might come handy. AppiumProxy is a python script that starts a web server, hooks to appium session creation requests, and delegates the handling of that session to a specific appium server instance. So you can have a single endpoint configured in your tests.

Keep in mind this is just a proof of concept and might be buggy. At the moment it has worked pretty well for me.

Dependencies
------------

My initial intention was to write this tool using only the standard lib. However, httplib and urllib2 are SO UGLY that I decided to go with [requests](http://docs.python-requests.org/en/latest/) instead. You can install it by running `pip install requests` or `easy_install requests`.

Starting the proxy
------------------

To bind the proxy to the default address (localhost:7777) run:

```
python appium_proxy.py
```

Or specify a host/interface and port. E.g.:

```
python appium_proxy.py -H 0.0.0.0 -p 1234
```

Then set your test project to connect to http://127.0.0.1:7777/wd/hub

Strategies to dispatch sessions to different Appium Servers
----------------------------------------------------------

You can define different session delegation strategies. The one I provide here by default is a simple round robin: You define a list of different appium servers and the session handling will be distributed among them in a round-robin fashion.

However you should be able to define your own very easily. E.g.:

 * Delegate sessions to different server instances based on the driver desired capabilities.
 * Have a pool of available/busy server instances, when all of them are busy block new session requests calls until one of the instances is released.
 * Create and destroy appium server instances on the fly.

You should be able to figure out how to implement your own by reading the code.


Environment Set Up for the round-robin dispatcher:
--------------------------------------------------

The location of the different appium servers are hardcoded in the script (I know that's ugly, but sorry, this is just a PoC):

```
SERVERS = [
    ("localhost", 4723),
    ("localhost", 4823),
    ("localhost", 4923)
]
```

This sample setting will require you to start 3 appium servers on different ports (keep in mind that you may need to define different port for other settings such as the chrome driver port). E.g.:

```
$ appium -p 4723 --chromedriver-port 9523
$ appium -p 4823 --chromedriver-port 9623
$ appium -p 4923 --chromedriver-port 9723

```


Some comments and thoughts
--------------------------

I've just tried this with Appium servers, however it should potentially work with any kind of selenium server. So you could have a single endpoint configured and forward calls to Selenium Grid or and Appium server depending on the driver's capabilities.

License
-------

[MIT License](http://opensource.org/licenses/MIT), so you are free do pretty much whatever you want with this.
