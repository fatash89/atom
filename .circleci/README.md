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

If the build and tests pass, the images will be pushed to dockerhub. Depending
on the branch, they will be tagged as so:

| branch | tag |
|--------|-----|
| `master` | `master-${CIRCLE_BUILD_NUM}` |
| `master` | `latest`
| Non-`master` | `development-${CIRCLE_BUILD_NUM}` |

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
| `DOCKERHUB_ORG` | yes | Organization you want your docker containers pushed to |
| `DOCKERHUB_REPO` | yes | Which repo in `DOCKERHUB_ORG` to push to |
| `DOCKERHUB_USER` | yes | Username of the account with permissions to push to your build repos. It's recommended to make a separate user for this so you don't risk exposing your personal credentials |
| `DOCKERHUB_PASSWORD` | yes | Password for `DOCKERHUB_USER`. Will be injected into the build and used to login. |

### Config File

Your config file for your project should be located at `.circleci/config.yml`.

#### Example Config

```yaml
  version: 2.1

  orbs:
    atom: elementaryrobotics/atom@x.y.z

  jobs:
    build:
      executor: atom/build-classic
      environment:
        DOCKER_COMPOSE_SERVICE_NAME: some_service
      steps:
        - checkout
        - atom/docker_login
        - atom/build_and_launch:
            file: docker-compose.yml
            service: ${DOCKER_COMPOSE_SERVICE_NAME}
        - run:
            name: Unit Tests
            command: docker exec -it ${DOCKER_COMPOSE_SERVICE_NAME} $my_unit_test_command
        - atom/store_image

  workflows:
    version: 2
    build-all:
      jobs:
        - build
        - atom/deploy-master:
            requires:
              - build
            filters:
              branches:
                only:
                  - master
        - atom/deploy-dev:
            requires:
              - build
            filters:
              branches:
                ignore:
                  - master
```

#### Explanation

In the above file we're doing the following:

1. Importing the `elementaryrobotics/atom` orb from CircleCI at the pegged version.
2. Defining our build job. In general you'll want all of these steps, with the exception of the Unit Tests step if you don't have any written. You should write and deploy unit tests!
3. Defining our workflows. Here, we always build and push to Dockerhub, though we push different tags for master and non-master branches.


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

## v0.0.3
##### New Features
- New command for installing and authentication of Git LFS.

##### Bug Fixes
- The `deploy-dev`, `deploy-master`, and `deploy-tag` jobs were fixed to include workspace attachment and docker login steps.


## v0.0.2
##### Changes
- Builds on GitHub tags
  - Will push Docker images tagged with `<GitHub tag>`, `master-<CircleCI build num>`, and `latest`
- Orb commands are parameterized for increased flexibility of use
  - Default parameters have been set so
- Commands for pushing individual dev/master/tag images without repeating workspace attachment and docker login (as in existing jobs)
- New `load_image` command for us in the above that does not include workspace attachment or docker login

##### Known Bugs
- The `deploy-dev`, `deploy-master`, and `deploy-tag` jobs do not include workspace attachment or docker login. Orb should be upgraded to v0.0.3 if using these jobs.
