FROM grafana/grafana

# Use root user -- easier/better able to store configs locally.
# THIS SHOULD NOT BE USED FOR NON-LOCAL SETUPS
# (but is fine for local setups)
USER root

# Install our rewuirements
RUN apk update && apk add git go npm python3 py-pip

# Install Mage
RUN mkdir -p /root/go/bin && git clone https://github.com/magefile/mage && cd mage && go run bootstrap.go

ENV PATH=/root/go/bin:${PATH}

# Get the grafana go plugin
RUN go get -u github.com/grafana/grafana-plugin-sdk-go

# Get the redis datasource
ADD grafana-redis-datasource /tmp/grafana-redis-datasource
WORKDIR /tmp/grafana-redis-datasource

# Install yarn and dependencies, build JS
ARG NODE_ARCH=x86
ENV npm_config_arch=${NODE_ARCH}
RUN npm install yarn -g && yarn install && yarn build

# Build and install plugin
RUN mage -v
RUN mv dist/ /var/lib/grafana/plugins/redis-datasource

# Note that we should allow loading unsigned plugins
RUN sed -i "s/;allow_loading_unsigned_plugins =/allow_loading_unsigned_plugins = redis-datasource/g" /etc/grafana/grafana.ini

# Install scripts we'll use to auto-create dashboards
ADD dashboards /metrics/dashboards
WORKDIR /metrics/dashboards
RUN pip3 install -r requirements.txt

# Add in the launch script
WORKDIR /metrics
ADD launch.sh .

# Specify bash as the entrypoint and the command as launch.sh
ENTRYPOINT [ "/bin/bash" ]
CMD [ "launch.sh" ]
