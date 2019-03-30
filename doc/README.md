Atom Documentation
------------------

## Overview

This repository contains the high-level documentation for the `atom`
SDK. At a high level, it contains the following:

1. Information on docker and how we use it
2. Information on atom and the basics of the system
3. Information on each element we ship

## Viewing

### On the Web

The docs are currently published online [here](https://atomdocs.io). They are rebuilt and redeployed nightly as well as with every new merge into the `master` branch of this repo.

### Using Docker

#### Installing

In order to view the documentation, you need to install docker on your
system. For information on installing Docker, visit the official
[Docker Site](https://docs.docker.com/install/). Docker, and therefore
the entire atom system, is supported on Linux, MacOS and Windows.

#### Launching

Our documentation is packaged and shipped as a webserver in a docker
container. Once you've installed docker on your platform, run the
following command on your system to launch the documentation server:

```
docker run -e "PORT=4567" -p 4567:4567 elementaryrobotics/atom-doc
```

This will launch the server and map port `4567` from within the server
to your machine. Note that this command works on Linux and hasn't been
tested on MacOS or Windows, but should work.

#### Viewing

Once the server is up and running, simply visit
[http://localhost:4567](http://localhost:4567) in your browser and you
should be up and running with the docs! The rest of the info that you
need is contained within the documentation itself.

## Deploying

Currently, CircleCI is set up to deploy the built docker container to Heroku.
Heroku is configured to deploy the container in the same way that we are running
the container so what we see in development should be what we get in deployment.

## Developing

It's recommended to do all development within the docker container as
well so that what you're developing is what gets deployed and there
are no issues with version mismatches, etc.

We use `docker-compose` to make the development easier. It will
automatically rebuild the docker container and set up all ports
and filesystem links.

### Rebuilding the Docker Container

If you make changes to dependencies or anything slate/ruby related
you'll want to rebuild the docker container. This will be largely
unecessary for the most part, but might be useful. To rebuild the
container you'll want to run:

```
docker-compose build --pull
```

### Launching the server

To launch the server, simply run:

```
docker-compose up -d
```

This will launch the container and run it in the background. You can
then see the instance and make sure it's up and running using

```
docker container list
```

### Running the Server

There are two ways to run the server:

1. Using `bundle exec middleman server`. This is slow, each page load will take
about 10s, but it
is responsive to changes and therefore best for development. When you launch the
server using `docker-compose` you'll see that this is how it is launched.
2. Using `bundle exec middleman build && thin start -c server -p 4567`. This
compiles the site to its static content and then uses `thin` to serve it. This
is what we do in production when the app is deployed. This method, however,
won't be responsive to changes and will cause you to need to re-run the command
if you want your changes to be picked up.

### Viewing Changes

As you make changes to the markdown, your changes will generally show
up in your web browser with a simple reload of the page. Slate seems
to re-parse the docs each time it loads the page which might explain
why it's so slow...

If you're having trouble seeing changes, you can try restarting the
docs service with:

```
docker-compose restart
```

This will restart the container/server.

### Shutting Down the server

Once you're done developing, you can shut down the server with

```
docker-compose down -t 1
```

### Adding Static Files

As the walkthrough is being modified, it's nice to be able to add in static
files that can be downloaded. To do this, follow the below steps:

1. Add the file to the `files` directory
2. Add the below line to the `config.rb` file:
```
# Import static files for deploying to the site
import_file File.join( __dir__, 'files', '$myfile'), '$myfile'
```
3. In the docs, when you want the user to download the file, add a link like
below:
```
<a href="/$myfile" download>here</a>
```

See the [Walkthrough](source/includes/walkthrough.md) for an example
of this with `atombot.py`.
