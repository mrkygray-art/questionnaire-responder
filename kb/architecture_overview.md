# Architecture Overview

## ARC-2.1 Tenant isolation
Customers are logically separated. A tenant identifier is enforced on every database query at the row level.

## ARC-2.2 Tenancy model
The platform is multi-tenant with logical separation. A dedicated single-tenant deployment option is not available.

## ARC-3.2 Controller connectivity
Controllers connect outbound only, over mutual TLS on port 443, using per-device certificates. No inbound firewall ports are required.

## ARC-4.1 API rate limits
The REST API has a rate limit of 600 requests per minute per tenant.

## ARC-4.3 User provisioning
SCIM automated user provisioning is not currently supported. Users are managed manually, through CSV import, or through the API.

## ARC-4.4 Video management integration
There is no native integration with video management systems at this time. Door events can be forwarded to other systems through webhooks.

## ARC-5.2 Log retention
Retention. Audit logs and door event logs are retained online for 90 days. Older logs are not available through the console.

## ARC-6.1 Availability design
The platform is designed for 99.9% availability. This is a design target.

## ARC-6.2 Service level agreement
Northgate does not currently offer a contractual uptime SLA with service credits.
