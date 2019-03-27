#!/bin/bash
bundle exec middleman build && thin start -c server -p $PORT
