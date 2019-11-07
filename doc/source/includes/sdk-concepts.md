# SDK Concepts

## Nucleus
The nucleus is the core of the atom system. It runs a redis server that enables elements to communicate with one another.

## Element
An element uses the atom library to provide functionality to other elements. This functionality includes reading/writing data to a stream and implementing a command/response system.

For example, one could implement a robot element that publishes its current state on a stream. This robot element could also contain a set of commands that tell the robot to move to a certain position in space. In addition to the robot element, one could have a corresponding controller element to consume the state of the robot and command it to move accordingly.

Each element is packaged as its own Docker container which sends and receives all of its data using the nucleus. This containerization allows each element to be developed with its own dependencies while simultaneously interacting with other elements with their own dependencies.

## Command
Issued by an element to execute some functionality of another element.

## Response
Returned by an element to indicate the results of the command to the caller element.

## Entry
A timestamped data packet that is published by an element on a stream that can contain multiple fields of data. The atom system is not concerned with the serialization of the data and leaves it as the responsibility of the developers to know how the data was serialized in the element. Our recommendation for serialization is msgpack as it is supported by the major programming languages.

## Stream
Data publication and logging system used by atom. A stream keeps track of the previously published entries (up to a user-specified limit) so that elements can ask for an arbitrary number of entries.

## Reference
A unique string that acts as a pointer to data in the atom system. Allows the
user to convert data that is temporarily available in a stream (but will
eventually be overwritten) into a permanent pointer (with optional auto-timeout)
so that it can be passed around between elements with the guarantee that the
data exists for as long as it's needed, no more, no less. Optimizes data flow
in the system such that for commands/responses that move around large binary
data blobs (such as images), the blobs aren't being copied excessively and don't
make the logs unreadable.
