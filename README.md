# artifactory

- an example on how to manage third party dependcies for internal systems

## Description

Use renovate to manage the versions, review Pull Requests as needed. Create workflows to build and/or push to internal/private registries. Implement scanning for security and validation requirements.

**Notes**: 
- Logic to handle ingestion has been left out but the basics needed to get started are available. 
- Use `helm template | grep "image:"` to get a list of images used in a chart 

## Usecases

- helm
- docker images

## Tools

- renovate
- github actions
- python


