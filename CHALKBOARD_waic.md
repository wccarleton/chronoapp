# WAIC and alternative phase assignments

Yes—you’re right. **My earlier requirement to keep phase memberships identical was too restrictive.**

For each event $i$ and posterior draw $\theta$, we evaluate:

$$
\log p(y_i\mid\theta,M)
=
\log\int p(y_i\mid t_i)\,
p(t_i\mid\theta,\text{assigned phase},M)\,dt_i
$$

Here $y_i$ is the observed measurement. The latent date is integrated out; WAIC then combines these event-level contributions with its variance penalty. This follows the integrated predictive approach for latent-variable models. [Method reference](https://arxiv.org/abs/1404.2918)

**Assigning an event to A versus B can therefore define two competing model specifications.** You can refit both and compare WAIC, provided both score the same observed events using the same measurement conventions and event-level prediction target. Labels need not remain identical when they encode the hypothesis being compared.

Two qualifications matter:

- Changing labels must not accidentally exclude events from one run—the UI currently selects events matching defined phase labels.
- If assignments are chosen by searching the observed dates for the lowest WAIC, that selection introduces additional optimism that ordinary WAIC does not account for.

The current calculation already supports such comparisons. The UI and documentation’s “identical memberships” wording should be relaxed; the score evaluates the measurements conditional on each proposed assignment, rather than predicting the labels themselves.
