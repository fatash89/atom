# CircleCI

## Overview

If you've successfully set up your build system using our CircleCI config
and orb you should have a continuous integration and deployment system
tied in with dockerhub fairly easily and quickly!

In general, what happens with the build system is this:

1. Each time you push to github, CircleCI will launch a new build
2. CircleCI should build your docker-compose file and launch all of the containers
3. You should build/write tests and add them to the build job
4. If the build is successful it will deploy the image to dockerhub. The standard tag for an image is explained in the table below.
5. The image built will also be archived on CircleCI so you can download it
and test without going through Dockerhub if you prefer.

Upon pushing to github, a build will be started on CircleCI. This will build
both the nucleus and atom images and will run any implemented unit tests
against them.

### Legacy Tags

If the build and tests pass, the images will be pushed to dockerhub. Depending
on the branch, they will be tagged as so:

| branch | tag |
|--------|-----|
| `latest` | `latest-<< pipeline.number >>` |
| `latest` | `latest` |
| Non-`latest` | `development-<< pipeline.number >>` |
| tag, i.e. v1.3.1 | `v1.3.1` |

Where `<< pipeline.number >>` is the CircleCI pipeline number for the build
that can be seen when using CircleCI's new UI. Each push to github generates
one pipeline with a unique, monotonic increasing number.

### Recommended Tags

Our build system now has a concept of a `variant` and a `platform`. Along with
the legacy tags (which can hopefully eventually be deprecated as they're not
specific), we push the following tags:

| branch | tag |
|--------|-----|
| `latest` | `latest-<< pipeline.number >>-<< variant >>-<< platform >>` |
| `latest` | `<< variant >>-<< platform >>` |
| Non-`latest` | `development-<< pipeline.number >>-<< variant >>-<< platform >>` |
| tag, i.e. v1.3.1 | `v1.3.1-<< variant >>-<< platform >>` |

You are encouraged to switch to using the new tag scheme as it will help as
we add more ARM support into our ecosystem.

## Configuration

### Steps

In order to hook into and set up the above process, you'll need to do the
following:

1. Set up a repo on dockerhub
2. Start building the project on CircleCI
3. Set up the environment variables for your project on CircleCI
4. Set up your `.circleci/config.yml` file to build/deploy using the `elementaryrobotics/atom` orb

### Environment Variables

| Variable | Required? | Description |
|----------|-----------|-------------|
| `DOCKERHUB_USER` | yes | Username of the account with permissions to push to your build repos. It's recommended to make a separate user for this so you don't risk exposing your personal credentials |
| `DOCKERHUB_PASSWORD` | yes | Password for `DOCKERHUB_USER`. Will be injected into the build and used to login. |

### Config File

Your config file for your project should be located at `.circleci/config.yml`.

#### Example Configs

Please see the CircleCI [example](../template/.circleci/config.yml) in the
example element template. This shows a basic example.

For more advanced and/or other examples, please see the `examples` section
of the [Atom orb](atom.yml).

## Atom Orb

We maintian a single orb (for now) in `atom.yml`. It lives on the public CircleCI orb repo at [`elementaryrobotics/atom`](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom). It contains some shortcuts that are nice for designing build/deploy workflows across elements.

In order to make changes to the orb and get them published the steps are:

1. Create a PR with the orb changes
2. Put up the PR and tag a member of the ER team
3. Once the PR is approved and merged we'll go ahead and push the changes.

### Creation

THIS ONLY NEEDS TO BE DONE ONCE. It's already been done and is included here only for reference.

```
circleci orb create elementaryrobotics/atom
```

### Validation

Always validate an orb before publishing it

```
circleci orb validate atom.yml
```

### Publishing

First, publish to dev

```
circleci orb publish atom.yml elementaryrobotics/atom@dev:some-tag
```

Then, when ready, promote to production (limited to ER staff only)

```
circleci orb publish promote elementaryrobotics/atom@dev:some-tag patch
```


### Release Notes

#### [v0.3.2](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.3.2)

##### New Features

- Upgrades buildkit to v0.8.3 and makes buildkit version independent from CircleCI machine image version.
- Hopefully fixes missing layer bug with the buildkit upgrade.

#### [v0.3.1](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.3.1)

##### New Features

- Adds in `stage` argument for test + deploy. This argument is unused in the commands and the command functionality remains unchanged, but it's useful for configuring build matrices to ship different stages to different places.

##### Upgrade Steps

None required

#### [v0.3.0](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.3.0)

##### New Features

** MAJOR CHANGES **

- Updates atom orb with significant changes to leverage new ARM executors in CircleCI as the primary/only executor type. Cross-compiling ARM images on intel machines is no longer supported. This effectively deprecates the need for the `platform` argument that was previously prevalent in the build, as we will determine our build platform from the instance type we're running on, intel or ARM. As such, major rework was done to the orb to remove the `platform` parameter.
- Brings in for the first time multi-arch deploys. The deploy stage will now be able to wait for both intel + arm builds to complete and then push both images under a single tag to Dockerhub. This means that you can use the same tags in intel + ARM, and docker will auto-pull the correct one for your platform.
- Deprecates the need for the `variant` concept in the orb. Instead of pushing intermediate/build tags with `-<< variant>>-<< platform >>`, intermediate tags are now just `-$(arch)` where `$(arch)` is either `x86_64` or `aarch64` depending on the platform. This obfuscates the tagging a bit less and makes the intermediate tags more understandable on most repos which didn't need/use the variant concept.
- Removes the double-build of dockerfiles that was added to protect against intermediate cache push failures. The cache push failures seem to be resolved/less prevalent, and the double-build was potentially exacerbating an issue where we would drop layers in docker images randomly.
- Orb has been restructured/simplified to remove the multiple build paths. All build paths now go through `buildx` and original/legacy docker building is not supported.

##### Upgrade Steps

Because of the changes, it's easiest to just make a wholesale change to a new template. From this release on, we'll now have templates in the [templates folder](templates) of this repo. There are two templates in this release:

| Template Name | Description |
|---------------|-------------|
| `config_basic.yml` | Basic element template for elements with a single-stage Dockerfile |
| `config_prod_and_test.yml` | Advanced element template for elements with `prod` and `test` stages in their dockerfile. It's recommended to upgrade to this template and update your element's dockerfile to have a `prod` stage which is what should ship and a `test` stage which includes test dependencies |

All templates can be used by just implementing the commented TODOs. This is typically just three pipeline variables:

| Variable Name | Description |
|---------------|-------------|
| `dockerhub_repo` | Full path to dockerhub repo (including organization) that we should be pushing builds to |
| `atom_tag` | Tagged atom release we should be feeding into the Dockerfile, such as `v1.2.3` |
| `atom_type` | One of ["", "-cv", "-cuda", "-vnc"] to indicate which atom build we want to be working atop |

To upgrade, you need only pick your template to work off of and use it as a basis. For simple elements, it should be able to fully replace the existing config file. For more complicated elements, use it as a guide.

When using templates the goal is to only need to have the user modify the **parameters** section. The aliases section should typically be left as-is and is part of the template.

#### [v0.2.0](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.2.0)

##### New Features

- Adds in the ability to build ARM with CircleCI's new ARM linux executors. This speeds up ARM builds by roughly 10x as they're no longer done in QEMU/simulation.

##### Upgrade Steps

In previous versions, to build ARM, one would set up a job in a .circleci file similar to:

```
  - atom/build_buildx:
      name: "build-<< matrix.platform >>-<< matrix.stage >>"
      matrix:
        parameters:
          platform: [ amd64, aarch64 ]
      image_name: << pipeline.parameters.dockerhub_repo >>
      image_tag: build-<< pipeline.number >>-<< matrix.stage >>
      cache_repo: << pipeline.parameters.dockerhub_repo >>
      cache_tag: build-cache
      build_args: --build-arg ATOM_IMAGE=<< pipeline.parameters.atom_repo >>:<< pipeline.parameters.atom_version >>-<< pipeline.parameters.atom_variant >>-<< matrix.platform >>
      filters:
        tags:
          only: /.*/
```

Now, we need to change the `matrix` section to include information about the `executor`. In order
to minimize disruption, we require both the `executor` and `platform` information, even
though they're technically redundant. This can be improved in a future release. We need to then
have our build jobs look like

```
  - atom/build_buildx:
      name: "build-<< matrix.platform >>-<< matrix.stage >>"
      matrix:
        parameters:
          platform: [ amd64, aarch64 ]
          executor: [ atom/build-ubuntu, atom/build-ubuntu-arm]
          exclude:
            - platform: amd64
              executor: atom/build-ubuntu-arm
            - platform: aarch64
              executor: atom/build-ubuntu
      image_name: << pipeline.parameters.dockerhub_repo >>
      image_tag: build-<< pipeline.number >>-<< matrix.stage >>
      cache_repo: << pipeline.parameters.dockerhub_repo >>
      cache_tag: build-cache
      build_args: --build-arg ATOM_IMAGE=<< pipeline.parameters.atom_repo >>:<< pipeline.parameters.atom_version >>-<< pipeline.parameters.atom_variant >>-<< matrix.platform >>
      filters:
        tags:
          only: /.*/
```

The exclude section is necessary so that we get exactly two build jobs, one for
`amd64` with `atom/build-ubuntu` and one for `aarch64` with `atom/build-ubuntu-arm`.

This only needs to be done on `build_buildx` jobs, the deploys can all be done on Intel without
any performance hit and without issue.

#### [v0.1.12](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.12)

##### New Features

- Upgrades `build-ubuntu` machine to `ubuntu-2004:202101-01`. This brings in Docker v20.10.2 and Docker Compose v1.28.2. The goal is to mitigate a bug in previous versions which caused files/layers to be missing from the final step in a Dockerfile.
- Minor internal build stability improvement. Might reduce job failures due to `buildx` not running properly.

##### Upgrade Steps

- No action needed.

#### [v0.1.11](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.11)

##### New Features

Adds in labels to all Docker images built. The following labels are added to all docker images:

| Label | Description |
|-------|-------------|
| `com.elementaryrobotics.branch` | Git branch the image was built off of|
| `com.elementaryrobotics.build_num` | CircleCI build number the image was built off of |
| `com.elementaryrobotics.build_url` | URL to the CircleCI build for the image|
| `com.elementaryrobotics.commit` | SHA1 of git commit for the image |
| `com.elementaryrobotics.repo` | Git reposity for the image |
| `com.elementaryrobotics.tag` | Typically blank, will be non-blank if this is a build run due to a new tag. |
| `com.elementaryrobotics.describe` | Output of `git describe --tags`  for the build |

Labels can be seen using `docker image inspect` on any image.

##### Upgrade Steps

- Upgrade to new orb only, no other action required

#### [v0.1.10](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.10)

##### New Features

- Adds in `check_formatting` command:

```
  - atom/check_formatting
```

Basic config, added to workflow as above will run `black` and `flake8` checks on the entire repository with no exclusions. To customize exclusions (see flake8/black docs for string syntax):

```
  - atom/check_formatting
      flake8_exclude: "dir1,dir2"
      black_exclude: "dir1|dir2"

```

To turn off `black` and only check `flake8`:
```
  - atom/check_formatting
      use_black: ""
```

- The above deprecates the previous `atom/check_flake8` command.

##### Upgrade Steps

- Replace your `atom/check_flake8` commands with `atom/check_formatting` as described above.


#### [v0.1.9](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.9)

##### New Features

- Replaces `master` with `latest`
- Changes `deploy_master` job to `deploy_release`
- Adds default `target_tag` of `""` to deploy commands

#### [v0.1.8](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.8)

##### New Features

- Fixes bug in deploy when using different target and source images

#### [v0.1.7](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.7)

##### New Features

- Adds in `use_git_lfs` for test command

#### [v0.1.6](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.6)

##### New Features

- Adds `use_git_lfs` option to builds. If set to `true`, will install `git-lfs`
on the machine before `checkout` so that the proper files are downloaded.

##### Upgrade Steps

Use in your workflows like below:
```
      - atom/build_buildx:
          name: "build-<< matrix.platform >>"
          matrix:
            parameters:
              platform: [ amd64, aarch64 ]
          image_name: << pipeline.parameters.dockerhub_repo >>
          image_tag: build-<< pipeline.number >>
          cache_repo: << pipeline.parameters.dockerhub_repo >>
          cache_tag: cache
          use_git_lfs: true
          filters:
            tags:
              only: /.*/
```

### Release Notes

#### [v0.1.5](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.5)

##### New Features

- Fixes `test` command/job for `aarch64`
- Updates/tweaks to examples

#### [v0.1.4](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.4)

##### New Features

- Adds in a `deploy_image_no_variant_platform` command/job. Useful if you
have a deploy that doesn't need the -<< variant >>-<< platform >> added on
such as in the Atom base deploys.

#### [v0.1.3](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.3)

##### New Features

- Large overhaul/restructure of the orb for better integration with new
CircleCI features such as pipelines and matrix configurations.
- Atom orb now should mainly be used with the following commands: `atom/build_buildx`,
`atom/test`, `atom/deploy`, and `atom/deploy_latest`. This should suit the needs of most users. There
are sub-commands broken out in the orb if you need something slightly
different/special for your build.
- The only CircleCI vairables now needed are `DOCKERHUB_USER` and `DOCKERHUB_PASSWORD`.
All other variables have been moved to pipeline parameters in the `.circleci`
file to make it a bit easier to configure. Other build variables should
be removed from your project when possible.
- Atom orb now only depends on the `DOCKERHUB_USER` and `DOCKERHUB_PASSWORD`
hidden variables. Other than that everything is broken out to make it
more what's happening more clear to the user.
- Atom orb supports/recommends using matrix configuration for building
for multi-arch. All jobs support the following fields: `variant` and `platform`.
A `variant` is either "stock" (i.e. vanilla), "opengl", "cuda", etc. A `platform`
is currently either `amd64` or `aarch64`.
- `atom/deploy` now supports the `target_tag_cmd` field which allows you to
run a command-line text replacement (grep, sed, etc.) on the tag field. By
default, this field removes `-stock` and `-amd64` from the auto-generated tag
s.t. stock builds for intel machines produce tags such as "development-X",
"latest-X", etc. as before. The auto-generated tag for builds automatically
appends the variant and platform to the build product. In general you shouldn't
need to mess with this field as it's mainly a crutch to let us use the matrix
features and still get all of our tags as expected but you might want to
use it at some point.

##### Upgrade Steps

- Start with the example config from this file and that should work for basic
builds that don't install anything too custom.
- Replace `dockerhub_repo` in the parameters at the top with your desired
Dockerhub repo
- Replace `atom_version` in the parameters at the top with the version of
Atom that your element is building against. It's recommended to switch
to the latest version if upgrading your build dependencies.
- Update the `Dockerfile` in your repo to have a variable atom version base image
that it's built from. It should default to the current verson of atom,
but this variable will be injected by the build system based on the `atom_version`
parameter at the top of the file.
```
ARG ATOM_IMAGE=elementaryrobotics/atom:v1.3.0
FROM ${ATOM_IMAGE}
```

#### [v0.1.2](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.2)

##### New Features

- Moves `CIRCLE_WORKFLOW_ID` to `CIRCLE_WORKFLOW_WORKSPACE_ID`. This allows us to actually re-run pipelines from failed, since when doing this CircleCI creates a new workflow, but within the same workspace. As we now push tagged intermediate builds based on the workflow ID we can re-run test stages.

##### Upgrade Steps

- Replace every instance of `CIRCLE_WORKFLOW_ID` with `CIRCLE_WORKFLOW_WORKSPACE_ID` in your `config.yml` files.

#### [v0.1.1](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.1)

##### New Features

- Improved tagging clarity. Now, `push_*_image` commands require full
tag to be specified instead of partial tag that's then injected into a
tag format. This makes it more clear/easier to use.

##### Upgrade Steps

- If specifying a custom tag for `push_*_image` commands, now you must specify
the entire desired tag in `target_tag`. If using the default tag, no action
is required

```diff
      - atom/push_dev_image:
          source_image: << parameters.repo >>:build-${CIRCLE_WORKFLOW_ID}<< parameters.tag >>
          target_image: << parameters.repo >>
          target_tag: development-${CIRCLE_BUILD_NUM}<< parameters.tag >>
```

#### [v0.1.0](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.1.0)

##### New Features

- Docker caching performance can be achieved through use of the `DOCKERHUB_CACHE_REPO` environment variable that must now be set in your build. This can be any repo on Dockerhub. The new `build_stage_buildx` builder will pull cache from and push cache to this repo automatically without having to rely on CircleCI for DLC and thus saving 200 credits/build without losing performance. It's recommended to adopt this new behavior. The cache repo can be the same repo as your production repo.
- Due to the above, DLC has been turned off in all machines
- `build-ubuntu` machine has been upgraded to the `202004-01` image as this is the first to ship with Docker 19.03+ which supports `buildx`
- Added `enable_buildx` and `build_stage_buildx` commands. `enable_buildx` must be run before `build_stage_buildx` on a machine. This uses the new `buildx` docker build engine which can cross-compile for different platforms as well as use external caches.
- Added `deploy_image` command

##### Upgrade Steps

- Reference the `v0.1.0` orb in your `config.yml`
- Set `DOCKERHUB_CACHE_REPO` in your CircleCI build to match your production repo
- Switch your build commands to use `enable_buildx`, `build_stage_buildx`, and `run_compose` instead of using `build_and_launch`.

```diff
      - atom/enable_buildx

      - atom/build_stage_buildx:
          stage: atom-source
          image_name: ${DOCKERHUB_ORG}/${DOCKERHUB_ATOM_REPO}
          image_tag: build-${CIRCLE_WORKFLOW_ID}
          platform: linux/amd64
          build_args: --build-arg BASE_IMAGE=elementaryrobotics/atom:base
          cache_repo: ${DOCKERHUB_ORG}/${DOCKERHUB_CACHE_REPO}
          cache_tag: -cache

      - atom/run_compose
          file: docker-compose.yml
```

#### [v0.0.11](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.11)
Created 04/07/2020.

##### Bug fixes
- Run flake8 format check in custom docker image with git and ssh installed to fix failed builds on tags.

##### Upgrade Steps
- Reference the v0.0.11 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.11
```

#### [v0.0.10](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.10)
Created 03/12/2020.

##### New features
- Added `update_submodules` command so that all elements with submodules don't have to write their own.
- Parallelized `update_submodules` across 8 jobs s.t. it speeds up the clone a bit to save some build time/$$.

##### Upgrade Steps
- Reference the v0.0.10 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.10
```

- You can now use `atom/update_submodules` as a command in order to clone all submodules in your build. This
is typically done after the `checkout` step.

```diff
 build-atom:
     executor: atom/build-classic
     resource_class: large
     environment:
       <<: *atom_build_vars
     steps:
       - checkout
+      - atom/update_submodules
       - set_atom_version
       - atom/docker_login

       ...

```

#### [v0.0.9](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.9)
Created 03/12/2020.

##### New features
- Changed the flake8 format check command to a job that is run within the [`alpine/flake8` docker image](https://hub.docker.com/r/alpine/flake8).

##### Upgrade Steps
- Reference the v0.0.9 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.9
```

- Use the job for running `flake8` in your build config's workflow, preferably first requiring the build/test step to pass, and
  then requiring the `flake8` job to pass before deploying any images, as shown below. The job now runs in the `alpine/flake8`
  docker image, and the python version to use can be passed in as a parameter that will also be used as the docker image tag.
  Available python versions/image tags can be viewed on dockerhub [here](https://hub.docker.com/r/alpine/flake8/tags).

```diff
  jobs:
    - build:
        filters:
          tags:
            only: /.*/
+   - atom/check_flake8:
+       requires:
+         - build
+       version: 3.7.0
+       exclude: doc,*third-party
+       filters:
+         tags:
+           only: /.*/
    - atom/deploy-latest:
        requires:
-         - build
+         - atom/check_flake8
        filters:
          branches:
            only:
              - latest
          tags:
            only: /.*/
```

#### [v0.0.8](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.8)
Created 03/09/2020.

##### New features
- Added a command for installing and running flake8 linter on repository code.

##### Upgrade Steps
- Reference the v0.0.8 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.8
```

- Use the new command for installing and running `flake8`, optionally specifying which directory to run it in and which directories to exclude from the check.
  As when running `flake8` locally, the directory to run it from must have a trailing slash. It is recommended to test `flake8` locally before configuring the build.

```
  - atom/check_flake8:
      directory: src/
      exclude: doc,*third-party
```

#### [v0.0.7](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.7)
Created 02/19/2020.

##### New features
- Added a command for building a specific stage of a multi-stage docker image.
- Added a command for launching a docker-compose file without building any images.
- Added a command for pushing an image.

##### Upgrade Steps
- Reference the v0.0.7 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.7
```

- Use the new command for building a stage of an image:

```
  - atom/build_stage:
      file: Dockerfile-atom
      stage: prod
      image_name: ${DOCKERHUB_ORG}/${DOCKERHUB_ATOM_REPO}
      image_tag: build-${CIRCLE_WORKFLOW_ID}
```

- Use the new command for launching a docker-compose file without building:

```
  - atom/run_compose:
      file: .circleci/docker-compose-circle.yml
      build_args: ""
```

- Use the new command for pushing an image:

```
  - atom/push_image:
      image_tag: ${DOCKERHUB_ORG}/${DOCKERHUB_REPO}:build-${CIRCLE_WORKFLOW_ID}
```

#### [v0.0.6](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.6)
Created 02/10/2020.

##### New features
- Since our CircleCI plan now allows for docker layer caching, removed the `--no-cache` flag from the docker build command.
- Replaced docker image save to and load from CircleCI workspace for transferring images between jobs with push to and pull from our docker registry.
  - Timing tests showed the push/pull from the registry to be faster than saving/loading from the workspace.

##### Upgrade Steps
- Reference the v0.0.6 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.6
```

- In order to have the docker push/pull between jobs work correctly, replace the `store_image` step in the build job with a `tag_and_deploy` step with the following `target_image` and `target_tag` params:

```diff
  build:
    executor: atom/build-classic
    steps:
      - checkout
      - update_submodules
      - atom/docker_login
      - atom/build_and_launch:
          file: docker-compose-circle.yml
          service: ${DOCKER_COMPOSE_SERVICE}
          image_tag: ${DOCKERHUB_REPO}-${CIRCLE_WORKFLOW_ID}
-     - atom/store_image:
-         image_filename: ${DOCKERHUB_REPO}
-         image_tag: ${DOCKERHUB_REPO}-${CIRCLE_WORKFLOW_ID}
      - run_tests:
          container: ${DOCKER_COMPOSE_CONTAINER}
+     - atom/tag_and_deploy:
+         source_image: ${DOCKERHUB_REPO}-${CIRCLE_WORKFLOW_ID}
+         target_image: ${DOCKERHUB_ORG}/${DOCKERHUB_REPO}
+         target_tag: build-${CIRCLE_WORKFLOW_ID}
```

These target params will be automatically used by the deploy jobs to pull this build image, re-tag it, and push to production.

#### [v0.0.5](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.5)
Created 02/05/2020.

##### Bug fixes
- Removed git commit hashes from deployed `latest` image tags

##### Upgrade Steps
- Reference the v0.0.5 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.5
```

#### [v0.0.4](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.4)
Created 01/31/2020.

##### New features
- New parameter for allowed time elapsed without output on docker push, `output_timeout`.
  - Available from all deploy commands and jobs. Defaults to 15 minutes.

##### Upgrade Steps
- Reference the v0.0.4 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.4
```

- Use the `output_timeout` parameter to specify a custom timeout on a command or job that performs a docker push and that requires an output timeout longer than the default of 15 mins:

```diff
  jobs:
    - atom/deploy-latest:
+       output_timeout: 20m
        requires:
          - build
        filters:
          branches:
            only:
              - latest
          tags:
            only: /.*/
```

#### [v0.0.3](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.3)
Created 01/30/2020.

##### New Features
- New command for install and authentication of Git LFS; use with `atom/install_git_lfs`.

##### Bug Fixes
- The `deploy-dev`, `deploy-latest`, and `deploy-tag` jobs were fixed to include workspace attachment and docker login steps.

##### Upgrade Steps
- Reference the v0.0.3 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.3
```

- To call the new `install_git_lfs` command, use the following:

```diff
steps:
+ - atom/install_git_lfs
```

#### [v0.0.2](https://circleci.com/orbs/registry/orb/elementaryrobotics/atom?version=0.0.2)
Created 01/31/2020.

##### New Features
- Added builds on GitHub tags.
  - Will push Docker images tagged with `<GitHub tag>`, `latest-<CircleCI build num>`, and `latest`.
- Orb commands parameterized for increased flexibility of use.
  - Default parameters have been set to preserve existing functionality.
- Added commands for pushing individual dev/latest/tag images without repeating workspace attachment and docker login (as in existing jobs).
- New `load_image` command for use in the above that does not include workspace attachment or docker login.

##### Known Bugs
- The `deploy-dev`, `deploy-latest`, and `deploy-tag` jobs do not include workspace attachment or docker login. Orb should be upgraded to v0.0.3 if using these jobs.

##### Upgrade Steps
- Reference the v0.0.2 orb in `config.yml` with

```
orbs:
  atom: elementaryrobotics/atom@0.0.2
```

- Add a job for building on GitHub tags with the following:

```diff
  jobs:
+   - atom/deploy-tag:
+       requires:
+         - build
+       filters:
+         branches:
+           ignore:
+             - /.*/
+         tags:
+           only: /.*/
```

- Update any `deploy-latest` jobs to also run on GitHub tags with the following:

```diff
  jobs:
    - atom/deploy-latest:
        requires:
          - build
        filters:
          branches:
            only:
              - latest
+         tags:
+           only: /.*/
```

- Update any jobs upstream of the `deploy-tag` job to also run on tags, for example:

```diff
  jobs:
-   - build
+   - build:
+       filters:
+         tags:
+           only: /.*/
```

It is required that all upstream jobs run on tags in order for the `deploy-tag` job to run.
