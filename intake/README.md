# PjLab intake with an external HTTPS address

The public Ingress accepts `POST /v1/cases` over HTTPS. Its ClusterIP Service sends the request to `server.py`, which checks a contributor upload token, limits each token to 10 submissions per minute, validates an 8 KiB case summary, and creates a private GitHub Issue in `bigshuaige1/agent-eval-data`. It returns an opaque receipt. Discovery archives and local artifact paths are never submitted.

## Values required from PjLab

- A namespace where a Deployment, Service, Ingress, and Secret may be created.
- An external DNS name that resolves to an Ingress controller reachable by contributors outside the cluster. A `.pjlab.org.cn` name is not automatically public; verify access from outside PjLab.
- A TLS Secret in that namespace whose certificate covers the DNS name, plus the Ingress class if no default class exists. Configure the controller to reject plaintext HTTP or redirect it to HTTPS; a TLS rule alone does not guarantee this.
- A registry image address the cluster can pull. The Dockerfile accepts `--build-arg PYTHON_IMAGE=...` if the default Python base image is unavailable.

The manifest uses the HTTPS proxy observed in the current PjLab environment for outbound GitHub API calls. Verify that `http://httpproxy-headless.kubebrain.svc.pjlab.local:3128` works in the deployment namespace; change the rendered manifest if the cluster uses a different proxy. The intake still sends case summaries to GitHub, so they do leave PjLab.

## Credentials

Create a fine-grained GitHub token scoped only to `bigshuaige1/agent-eval-data` with **Issues: write**. Use a secret manager to create a Kubernetes Secret named `agent-eval-intake` with keys `github-token` and `upload-token-hashes`. Never put token values in the manifest, image, shell command line, repository, chat, or logs.

Issue each contributor a separate high-entropy upload token through a secure channel. Put the SHA-256 hex digest of each token on its own line in `upload-token-hashes`; keep the raw token only in the contributor's secret manager. The following command prompts without putting the token in shell history and prints only its digest:

```bash
python3 -c 'import getpass,hashlib; print(hashlib.sha256(getpass.getpass("Upload token: ").encode()).hexdigest())'
```

Contributors configure `AGENT_EVAL_ENDPOINT=https://YOUR-HOST/v1/cases` and `AGENT_EVAL_UPLOAD_TOKEN` in their environment. They need no access to the private GitHub repository. To revoke one contributor, remove that digest from the Secret and restart the Deployment. The client keeps Enter or `ALWAYS` consent scoped to the endpoint and local store.

## Build and deploy

Use an approved CPU worker to build and push the image, then render a manifest containing no secrets:

```bash
docker build -t REGISTRY/agent-eval-intake:TAG -f intake/Dockerfile intake
docker push REGISTRY/agent-eval-intake:TAG
python3 intake/render.py --host YOUR-HOST --image REGISTRY/agent-eval-intake:TAG \
  --tls-secret YOUR-TLS-SECRET --output results/20260924_intake-deploy/app.yaml
```

Add `--ingress-class CLASS` to the renderer if your cluster has no default Ingress class. Review the rendered host, image, TLS Secret, proxy, namespace, and resource limits. Have a PjLab operator or the authorized user apply it in the selected namespace:

```bash
kubectl -n NAMESPACE apply -f results/20260924_intake-deploy/app.yaml
kubectl -n NAMESPACE rollout status deployment/agent-eval-intake
```

From a machine outside the cluster, an unauthenticated POST to `https://YOUR-HOST/v1/cases` should return HTTP 401. Verify that plaintext HTTP cannot accept a case. Then use a synthetic case with a contributor token to verify that a private Issue is created and its receipt is stored locally. Check DNS, certificate validity, Ingress routing, and GitHub proxy egress before sending real cases. A request timeout may still mean the Issue was created; reconcile by case ID before retrying.

This is a small single-process receiver. Its rate limit is in memory and assumes one replica. Restrict who receives upload tokens, review private Issues as untrusted submissions, and use your organization's HTTPS and data-handling rules for external contributors.
