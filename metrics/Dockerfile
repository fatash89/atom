FROM grafana/grafana:7.5.13

# Use root user -- easier/better able to store configs locally.
# THIS SHOULD NOT BE USED FOR NON-LOCAL SETUPS
# (but is fine for local setups)
USER root

# Configuration environment variables
ENV ATOM_NUCLEUS_HOST ""
ENV ATOM_METRICS_HOST ""
ENV ATOM_NUCLEUS_PORT "6379"
ENV ATOM_METRICS_PORT "6380"
ENV ATOM_NUCLEUS_SOCKET "/shared/redis.sock"
ENV ATOM_METRICS_SOCKET "/shared/metrics.sock"
ENV REDIS_CLI_BIN /usr/bin/redis-cli
ENV PYTHONUNBUFFERED=TRUE

# Install our requirements
RUN apk update && apk add alpine-sdk git go npm python2 python3 py-pip redis

# Install Mage
RUN mkdir -p /root/go/bin && git clone https://github.com/magefile/mage && cd mage && go run bootstrap.go

ENV PATH=/root/go/bin:${PATH}

# Get the grafana go plugin
RUN go get -u github.com/grafana/grafana-plugin-sdk-go

# Get the redis datasource
ADD metrics/grafana-redis-datasource /tmp/grafana-redis-datasource
WORKDIR /tmp/grafana-redis-datasource

# Install yarn and dependencies, build JS
RUN npm install yarn -g && yarn install && yarn build

# Build and install plugin
RUN set -x; mage -v build:linux$(arch | sed 's/x86_64//g' | sed 's/aarch64/ARM64/g')
RUN mv dist/ /var/lib/grafana/plugins/redis-datasource

# Add in our grafana config file
ADD metrics/grafana.ini /etc/grafana/grafana.ini

# Install scripts we'll use to auto-create dashboards
ADD metrics/dashboards /metrics/dashboards
WORKDIR /metrics/dashboards
RUN pip3 install -r requirements.txt

# Add in the launch script
WORKDIR /metrics
ADD metrics/launch.sh .

# Add in the script that lets us wait for the nucleus
ADD utilities/wait_for_nucleus.sh /usr/local/bin/wait_for_nucleus.sh

# Specify bash as the entrypoint and the command as launch.sh
ENTRYPOINT [ "/bin/bash" ]
CMD [ "/usr/local/bin/wait_for_nucleus.sh", "/bin/bash", "launch.sh" ]
