## 	Taking a Long Look at QUIC
### An Approach for Rigorous Evaluation of Rapidly Evolving Transport Protocols

**DISCLAIMER I:** this is NOT production level code! It is grad student code (!!!), developed under the pressure of deadlines and such! Furthermore, by nature this project consists of many parts (as described in the following sections), require attention to many small details to make sure things do what we expect them to do, and call for many hacks to make things work. So please do not expect a nice clean binary that you just double click! You need to setup servers, compile Chromium (16GB of code base!!!), etc. I will try to clean the code as much as possible, keep updating these instructions to make it easy to follow, and of course welcome any feedback/comments you have. However, I should also mention that I recently defended my PhD and left NEU for a full time job. So I won’t be maintaining this project full time, but it is being handed off to very talented junior PhD student in our group who will continue on with the project, and overseen by an amazing PI who won’t put anything out there unless he has 100.00% confident in it!

**DISCLAIMER II:** make sure you read and fully understand our IMC17 paper and understand exactly what the experiments try to achieve before trying to run any tests. Otherwise, the instructions below might not make much sense to you!

Ready to get your hands dirty? Enjoy! 😀

### About the code:
#### General notes:
* Servers side
    * You need to have a HTTP/2 and a QUIC server that can serve your content for the PLT tests. Ideally, run the servers on the same machine. 
    * For the HTTP/2 server, I used Apache2 (with HTTP/2 module) and Flask, but you can use any other server as you see fit. However, I suggest using HTTP/2, as that is the fair apples to apples comparison as HTTP over QUIC is basically using an HTTP/2 API, unless you intentionally want other comparisons.
    * For the QUIC server, I use the QUIC toy server included in Chromium. According to Google, this server is NOT performant. However, this is mostly due to not being multiprocess. Our tests show that if only one client is accessing the server at a time (which is the case in our tests), the toy server’s performance is not and issue.
    * Note that you need to have signed certs (trusted by your browser) for both HTTP/2 and QUIC servers (you can of course have self-signed certs and add them to the list of trusted CAs on the client side).
* Client side
    * For the client, I use Chromium browser. [Here](https://chromium.googlesource.com/chromium/src/+refs) is the list of all Chromium versions. I suggest using the stable release for the version you’re using. [Here](https://googlechrome.github.io/current-versions/) you can find the latest version number for all release channels. 
    * Note that each Chromium version only supports a range of QUIC versions. In your Chromium source, you can check this file to see which QUIC versions it supports. 
    * I strongly suggest building the Chromium browser and quic_server from the same Chromium version.
    * I use chromedriver to drive the browser and chrome-har-capturer (version XXX) and gather network timing information (I have code for Selenium too, but I found that extracting detailed network timings with Selenium is not doable, or difficult—I haven’t explored this much). MAKE SURE TO READ THE LAST BULLET POINT IN THIS SECTION.
    * You need to make sure to use a chromedriver version that supports the Chromium version you’re using.
    * To do things headless, I use xvfb. However, apparently the latest version of chrome-har-capturer is headless! I haven’t tested things with it, but it can potentially make things cleaner and easier. If you want to use my script, you need to use the `chrome-har-capturer` version mentioned above. I am sure you can use the newest chrome-har-capturer too (the headless one), but you probably need to make some (most probably minor) changes to the script.
* Machines:
    * I use Ubuntu 14.04 for both client and server side. However, you should be able to use other platforms, especially UNIX based ones (although I haven’t tested them)
* Network emulation:
    * I perform all the network emulations on the client side
    * I use TC and NETEM for network emulations
    * Our experience shows that running network emulation with TC and NETEM on the client machine could be problematic. One example is the token bucket burst. We observed that when running a token bucket on the client machine, even when setting the filter so to not allow bursts, there we still bursts with a rate much higher than the token bucket rate at the beginning of the transfer. This will affect the PLT tests, especially if objects downloaded are small and the transfer can finish during the initial burst. To avoid this, we connect the client (using ethernet) to a router running OpenWRT and perform network emulations on the router.
    * I found that NETEM has issues on OpenWRT version Chaos Calmer 15.05. So I used the previous version, Barrier Breaker 14.07
    * Obviously you can use other network emulation tools for your tests (and we would love to know what you find, and if you observer that the results change based on the emulation tool used)
    * Note that the script uses SSH to connect to the router and configure the network emulation. So you have to make sure you have the ssh keys, config, … all configured properly so that the script can connect to your router.
* Mobile devices:
    * When running tests from a mobile device, I use Chrome for Android.
    * For driving the browser on a mobile device, I use ADB. I also use ADB to do port forwarding so `chrome-har-capturer` can connect to the browser’s debugging port on the mobile device and collect the HAR.
* Analyzing results:
    * Once you run QUIC vs. TCP back-to-back tests, there will be a HAR file for every test (quic_1.har, https_1.har, quic_2.har, https_2.har, …).
    * I generate heatmaps (similar to ones in the paper) using the average PLTs extracted from these files.
* MISC (but important):
    * Be aware of the policies of the networks you’re running tests with. We’re dealing with micro- and milli-seconds! Network management policies can greatly affect the results. Even at Northeastern, we found that different parts of the network with different policies resulted in vastly different results (in most networks if there are any restrictive policies, they usually target UDP!). So you need to be careful and know exactly how your network is treating your traffic. Ideally you want to run things in a well provisioned (or a testbed) network which doesn’t mess with your traffic.
Code details:

### Scripts:
* **pythonLib.py:** this file contains some functions that I use throughout the project
* **engineChrome.py:** this is the script you run on the client side. It opens the browsers, runs the tests, stores the results, … . This script uses Selenium. Remember that I used chrome-har-capturer for the paper. However this script includes functions that the chrome-har-capturer script uses. So it’s important!
    * You obviously need to tell the script the hostname of your servers. This is currently hardcoded in the script (ugh! but you can easily change this to and argument that is passed to the code. Once you get familiar with the code, you realize it is super easy to add arguments and pass them in the command line)
    * To give the server hostname, search for "Setting up the server hostnames” in the script. There is if/else clause right beneath it. Give a name to your server (e.g. myServer), update the if/else clause accordingly, and when running the script pass the name to the against argument (--against=myServer)
* **engineChrome_harCapturer.py:** this is the script you run on the client side that runs things using chrome-har-capturer.
* **doTCstuff.py:** this is the script responsible for running TC and NETEM commands for network emulations.
* **engineWrapper.py:** this is a wrapper script for engineChrome_harCapturer.py (or engineChrome.py). It runs network emulations, pre-PLT tests if set to True (iperf and ping tests), and the PLT tests (in that order).
* **chromeDrivers:** this is the folder that include different chromedriver versions for different Chrome versions. I have included one version here for your convenience. You are responsible of storing the versions you need in this folder. the naming convention is chromedriver_[version] (e.g. chromedriver_2.22). 
