# IT Infrastructure & Network

## Building WiFi

Meridian Business Center provides two WiFi networks:

**Meridian-Tenant** (secure, for daily work)
- SSID: Meridian-Tenant
- Security: WPA3 Enterprise
- Connection: Each tenant company receives unique login credentials (username + password per employee)
- Speed: Up to 500 Mbps shared per floor
- To request credentials for new employees: email it@meridian-breda.nl with employee name and company name

**Meridian-Guest** (open, for visitors)
- SSID: Meridian-Guest
- Security: Captive portal (accept terms of use)
- Speed: Up to 50 Mbps
- Automatically disconnects after 8 hours
- No access to internal building systems or tenant networks
- Not suitable for video conferencing or large file transfers

## Wired Network

Each office suite has Ethernet ports (Cat6a, 1 Gbps). Ports are located in the floor boxes (2 per suite) and wall plates (2–4 per suite depending on size). Ethernet provides faster, more stable connectivity than WiFi — recommended for video conferencing and large data transfers.

To activate an Ethernet port, contact it@meridian-breda.nl with your suite number and port location. Ports are activated within 1 business day. Each port is mapped to your company's VLAN for security isolation.

## Internet Service

The building has a dedicated fiber connection (KPN Business, 1 Gbps symmetric, redundant). The connection is shared among all tenants. Fair use policy applies — no single tenant should consistently consume more than 20% of total bandwidth.

If your company needs a dedicated internet line (e.g., for data-heavy operations or compliance reasons), you can arrange a private connection through KPN, Ziggo, or another ISP. Contact facility management for access to the building's telecom riser.

## Server Room

Room 411 (Floor 4) is the building's shared server/telecom room:
- Access: Restricted to authorized IT staff only (separate badge authorization required)
- Climate: Dedicated precision cooling, maintained at 20°C ± 1°C, 45% humidity
- Power: Dual-feed UPS (30 minutes runtime) + diesel generator (automatic switchover after 30 seconds of power loss)
- Fire suppression: FM-200 clean agent system (no water)
- Rack space: Available for tenant equipment (19" standard racks, from €150/month per 4U)

To request server room access or rack space, email it@meridian-breda.nl.

## Printing

Shared printers are available in the print rooms on each floor (1–4):
- Printer model: HP LaserJet Enterprise M507 (B&W) and HP Color LaserJet Enterprise M554 (color)
- Access: Print via WiFi (driver installation instructions available from reception)
- Paper and toner are provided as part of building services
- Scanning: Scan to email available on all printers
- Color printing is available but please use B&W for large documents to reduce costs
- Report paper jams or toner issues to reception — do not attempt to replace toner yourself

## Common IT Issues

**"WiFi is slow"**
1. Check if you're connected to Meridian-Tenant (not Guest)
2. Try moving closer to the access point (ceiling-mounted white disc)
3. Disconnect and reconnect to the network
4. If persistent, report to it@meridian-breda.nl with your floor and approximate location

**"I can't connect to WiFi"**
1. Ensure you have the correct credentials (company-specific)
2. Check that your device supports WPA3 (older devices may not)
3. Try "Forget network" and reconnect with fresh credentials
4. Contact it@meridian-breda.nl for credential reset

**"The printer is jammed / out of paper"**
Contact reception (+31 76 555 0100). The cleaning or FM team will resolve within 30 minutes during business hours.

**"I need WiFi credentials for a new employee"**
Email it@meridian-breda.nl with: employee full name, company name, expected start date. Credentials are delivered within 1 business day.

## Phone System

The building does not provide a centralized phone system. Each tenant company is responsible for their own telephony solution (VoIP, mobile, etc.). The building's internet connection supports VoIP traffic with QoS prioritization on the Meridian-Tenant network.

If you need a physical phone line (ISDN/POTS), contact KPN directly. Patch panel access is available in the telecom riser (contact FM for escort).

## Data and Privacy

Building WiFi traffic is not monitored or logged beyond standard network management (connection times, bandwidth usage per device). The building management does not have access to tenant data transmitted over the network. Network management is handled by CloudCT B.V. under a data processing agreement compliant with GDPR (AVG).
