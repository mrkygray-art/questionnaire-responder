# Security Policy

> STARTER KB. Reconstructed from the answer key and recorded answers because the original
> Northgate knowledge base was not available. Replace these files with the originals
> (keep the "## ID Title" heading format).

## SEC-2.1 Encryption in transit
All customer-facing and API traffic uses TLS 1.2 or higher. TLS 1.0 and 1.1 are disabled. Controller-to-cloud traffic uses mutual TLS.

## SEC-2.2 Encryption at rest
Databases, object storage, and backups are encrypted at rest with AES-256.

## SEC-2.3 Key management
Encryption keys are managed in the infrastructure provider's key management service and are rotated annually. Customer-managed keys (BYOK) are not offered.

## SEC-3.1 Single sign-on
The customer admin console supports single sign-on through SAML 2.0 and OpenID Connect (OIDC), including Microsoft Entra ID and Okta.

## SEC-3.2 Multi-factor authentication
MFA is mandatory for all Northgate staff. For customer administrators, MFA can be enforced by the customer through its identity provider or through the console's built-in MFA.

## SEC-3.3 Roles and permissions
The platform provides four predefined roles: Owner, Administrator, Operator, and Viewer. Custom roles are not currently available.

## SEC-4.2 Log retention
Log retention. Audit logs and door event logs are retained for 12 months.

## SEC-5.1 Data retention
Customer data is retained for the term of the customer's contract.

## SEC-5.2 Data deletion
On written request after contract termination, production customer data is deleted within 30 days.

## SEC-5.3 Deletion from backups
Deleted data is removed from backups as they age out under the normal backup cycle.

## SEC-5.4 Backups
Database backups are taken daily and retained for 35 days.

## SEC-7.1 SOC 2
Northgate does not currently hold a SOC 2 Type II report. A SOC 2 Type I readiness assessment is in progress, and no completion date has been committed.

## SEC-7.2 ISO 27001
Northgate does not hold an ISO 27001 certification.

## SEC-7.3 FedRAMP
Northgate does not hold a FedRAMP authorization and is not currently pursuing one.

## SEC-7.4 Penetration testing
An independent third party performs a penetration test of the platform annually. A summary letter can be shared under NDA on request. Detailed findings are not shared.

## SEC-7.5 Provider certifications
The infrastructure provider holds its own compliance certifications. These belong to the provider and are not certifications held by Northgate.

## SEC-8.1 Biometric data
Northgate does not collect or store biometric data, such as fingerprints or facial templates.

## SEC-8.2 Data residency
Customer data is hosted in United States regions only. Hosting in the EU or other regions is not available.

## SEC-9.1 Recovery objectives
Design targets: Recovery Time Objective (RTO) of 8 hours and Recovery Point Objective (RPO) of 24 hours.
