// Local QA Jenkins only.  Security is disabled because the HuntAI executor
// authenticates with HTTP Basic (empty user + API token); anonymous access
// makes that work without provisioning a Jenkins user for every developer.
// Never copy this file to a shared Jenkins.
import hudson.security.AuthorizationStrategy
import hudson.security.SecurityRealm
import jenkins.model.Jenkins

def instance = Jenkins.get()
instance.setSecurityRealm(SecurityRealm.NO_AUTHENTICATION)
instance.setAuthorizationStrategy(AuthorizationStrategy.UNSECURED)
instance.setCrumbIssuer(null)
instance.setQuietPeriod(0)
instance.setNumExecutors(2)
instance.save()
println("HuntAI QA Jenkins: security disabled, quiet period 0, 2 executors")
