[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $TenantId,

    [Parameter(Mandatory)]
    [string] $BlueprintName,

    [Parameter(Mandatory)]
    [string] $AgentName,

    [Parameter(Mandatory)]
    [string] $SponsorUserId,

    [switch] $UseDeviceCode
)

$ErrorActionPreference = 'Stop'
$graphBaseUrl = 'https://graph.microsoft.com/v1.0'

if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) {
    throw @'
Microsoft Graph PowerShell is required. Install it for your user with:
Install-Module Microsoft.Graph.Authentication -Scope CurrentUser -Force
'@
}

$scopes = @(
    'AgentIdentityBlueprint.Create'
    'AgentIdentityBlueprintPrincipal.Create'
    'AgentIdentity.Create.All'
)

function Invoke-AgentGraphPost {
    param(
        [Parameter(Mandatory)]
        [string] $Uri,

        [Parameter(Mandatory)]
        [hashtable] $Body
    )

    Invoke-MgGraphRequest `
        -Method POST `
        -Uri $Uri `
        -Headers @{ 'OData-Version' = '4.0' } `
        -ContentType 'application/json' `
        -Body ($Body | ConvertTo-Json -Depth 5)
}

$connectParameters = @{
    TenantId = $TenantId
    Scopes = $scopes
    NoWelcome = $true
}
if ($UseDeviceCode) {
    $connectParameters.UseDeviceCode = $true
}

Connect-MgGraph @connectParameters

try {
    $sponsorBinding = @("$graphBaseUrl/users/$SponsorUserId")
    $blueprint = Invoke-AgentGraphPost `
        -Uri "$graphBaseUrl/applications/microsoft.graph.agentIdentityBlueprint" `
        -Body @{
            displayName = $BlueprintName
            'sponsors@odata.bind' = $sponsorBinding
        }

    if (-not $blueprint.id -or -not $blueprint.appId) {
        throw 'Microsoft Graph response did not include the blueprint id and appId.'
    }

    $principal = Invoke-AgentGraphPost `
        -Uri "$graphBaseUrl/servicePrincipals/microsoft.graph.agentIdentityBlueprintPrincipal" `
        -Body @{ appId = $blueprint.appId }

    if (-not $principal.id) {
        throw 'Microsoft Graph response did not include the BlueprintPrincipal id.'
    }

    $agentIdentity = Invoke-AgentGraphPost `
        -Uri "$graphBaseUrl/servicePrincipals/microsoft.graph.agentIdentity" `
        -Body @{
            displayName = $AgentName
            agentIdentityBlueprintId = $blueprint.appId
            'sponsors@odata.bind' = $sponsorBinding
        }

    if (-not $agentIdentity.id -or -not $agentIdentity.appId) {
        throw 'Microsoft Graph response did not include the Agent Identity id and appId.'
    }

    [ordered]@{
        blueprint_application_id = $blueprint.appId
        blueprint_object_id = $blueprint.id
        blueprint_principal_object_id = $principal.id
        agent_identity_application_id = $agentIdentity.appId
        agent_identity_object_id = $agentIdentity.id
    } | ConvertTo-Json
}
finally {
    Disconnect-MgGraph | Out-Null
}