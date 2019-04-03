# Waveform Demo

This demo creates a `waveform` element in C++ which pubishes both serialized
and unserialized sin(x), cos(x) and tan(x) values on the streeams `serialized`
and `unserialized`, respectively.

The period of the waveform can be changed by sending the `period` command
with a msgpack'd float value. The frequency at which the waveform points
are published can be changed with the `rate` command. The default publishing
rate is 1kHz.

The demo also launches the `record` element, and the commands in the [documentation](https://atomdocs.io/#record) work nicely to test out the graphing features. The graphics can be seen using your browser if you navigate to `localhost:6080`.
