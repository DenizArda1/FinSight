
## Docker Compose

See [Docker setup](docker/README.md) for build/run commands, host Ollama connectivity,
persistent data and configuration. Build and launch from the repository root:

```sh
docker compose build
docker compose up -d
```

The interface is available at http://127.0.0.1:8766. Existing financial data and logs
are bind-mounted; local Ollama stays on the host. API credentials come from `.env`.

## GitHub Actions

`.github/workflows/ci.yml` runs Python tests, a JavaScript syntax check and Compose
validation on pushes and pull requests. After tests pass, it builds a Linux amd64
Docker image and checks container startup without calling models or external APIs.

To publish an image, open **Actions → FinSight CI → Run workflow** on the default
branch and enable **publish_image**. Successful checks are followed by publication to
`ghcr.io/<owner>/<repository>:sha-<commit>` and `:latest`, using GitHub's built-in
`GITHUB_TOKEN`. No application API keys are required in GitHub Secrets. Registry
publication is optional; it does not deploy the application or change package visibility.
Cloud deployment is not configured. Commit the workflow together with its application,
Docker and test dependencies before pushing.
