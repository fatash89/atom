# SDK Introduction

## High-Level

Atom is an SDK that allows for high-throughput messaging, logging, and command handling in a distributed system with language support in nearly every programming language. It allows creators of robots, IoT systems, small server deployments and more to quickly and easily develop reliable messaging systems with minimal effort across a few foundational paradigms.

Atom has been developed with both ease of use and performance in mind. Development and use of the Atom OS depends heavily on [Docker](https://www.docker.com/). This document will cover Docker at a high level mainly in areas that are applicable to atom users and developers.

On top of Docker, the main technology that atom uses is [Redis](https://redis.io/). Redis is the primary communication backend of the Atom OS and enables our cutting-edge communication paradigms. It also is the main driver of our language support as it's supported in 50+ programming languages. A high-level atom user/dev won't need to know much about Redis, while developers of our language clients will become intimately familiar with its many features.

## Goals

Atom was developed out of a desire for an easier, performant paradigm for reusable microservices. When developing the system we were focused on a few main goals:

1. Create an easy, performant command/response paradigm
2. Create an easy, performant data publication paradigm
3. Eliminate dependency issues
4. Enable use in as many programming languages as possible, on as many platforms as possible
5. Enable users to develop reusable applications
6. Make serialization optional by design, but when desired easy and performant

## Messaging

With the above goals in mind we first had to choose a messaging protocol and design a specification around it. Our system was originally built on [zeromq](http://zeromq.org/) which, while incredibly performant, would require a significant amount of custom code to implement the easy messaging paradigms we wanted. [ROS](http://www.ros.org/), on the other hand, has most of the concepts we needed, yet didn't quite meet our performance or ease-of-use requirements. After evaluating the technologies available we settled on using Redis, specifically [Redis Streams](https://redis.io/topics/streams-intro) as our primary messaging protocol.

Redis Streams are essentially in-memory time-series data stores that allow for both blocking and nonblocking interaction with data. The primary advantage they provide over a typical pub-sub socket is that Redis acts as a last value cache, i.e. it stores the most recent N items in a stream. Now, a subscriber can either choose to interact with the stream in traditional pub/sub fashion and get events whenever new data is delivered or they could also choose to poll the stream and request the most recent N events whenever they'd like. This is quite powerful as it eliminates many issues with pub/sub such as the [Slow Subscriber](http://zguide.zeromq.org/page:all#Slow-Subscriber-Detection-Suicidal-Snail-Pattern) and it allows publishers of data to truly decouple from all different sorts of subscribers.

Another advantage of Redis Streams are the consumer groups. With a consumer group, we can set up multiple subscribers on a single data stream where redis will handle distributing the N messages coming in over the stream to the M subscribers such that no two subscribers get the same message. This allows for load balancing, a/b testing and more paradigms with no additional effort.

Finally, Redis is a hardened technology with an active developer base which leads us to believe that building a system atop Redis will enable us to be more consistently stable and also give us the tools to fix the issues we see when they do arrive.

## Specification

With the messaging protocol chosen, the core of the Atom OS is a pair of specifications:

1. Messaging protocol atop Redis
2. End-user API

The language clients, then, will implement (1) while exposing (2) to the users in a consistent fashion. Most atom developers will mainly be concerned with (2), i.e. "How do we use atom?", while (1) is needed for developers to create and verify new language clients.

The full specification can be found in the [Specification](#sdk-specification-and-api) section of this documentation.

## Language Clients

A language client, then, implements the end-user API in the language of their choice. Users can choose to interact with the atom systems in a span of languages from C to javascript (coming soon!). For each supported language in the system you'll see a tab on the right hand side of this documentation that shows the implementation details for that particular language.

Some languages are more suited to some tasks than others and atom gives the user the flexibility to implement their desired task in their desired language. Elements requiring hardware or linux drivers, for example are typically written in C/C++ for performance, while many ML algorithms like to use Python and web-facing code is often written in javascript.

## Elements

The final concept in the Atom OS is that of an element. An element is a fully containerized microservice that utilizes an Atom OS language client to expose some novel functionality to the system. Some examples of elements are:

1. Realsense Camera Driver
2. Stream Viewer
3. Segmentation algorithm
4. Recording tool

Each element exposes its functionality through two main features of the Atom OS:

1. Commands
2. Data Streams

### Commands

Commands allow for one element to call functionality present in another element. Some example commands are:

- "Record stream X for Y seconds"
- "Take a snapshot of the camera"
- "Change the segmentation algorithm to Z"

Commands can take an optional data request payload and return an optional response payload.

Commands can be called in either a blocking or nonblocking fashion depending on the caller's preference.

### Data Streams

Data streams are published by elements for other elements to consume. For example the realsense element publishes streams of color, depth and pointcloud frames at 30Hz.

Using Redis Streams, the publisher is able to publish completely agnostic to any subscribers and/or their preferred subscription method. The subscribers can then choose to subscribe to all data in an event-driven fashion, poll at their desired frequency for the most recent value, or traverse the stream in large chunks, querying for all data since they last read.

Each piece of data in a stream is called an "Entry".
