# Troubleshooting

## A change was refused

Warden refuses a change that would lock the person making it out.

| Error code | Message | What to do |
| :--- | :--- | :--- |
| `lose_admin` | The change would take away your own administrator access | Ask the owner or another administrator to make it |
| `requires_your_mfa` | The change would lock you out right away because you haven't set up 2FA | Set up 2FA on your profile's Security page first, or allow a grace period |
| `invalid_member` | The user can't be managed | The owner and system users can't be added to groups |

## Two-factor authentication can't be enforced

This repair appears when 2FA is required but no 2FA module is loaded. Warden restricts nobody until one is available. Add a module, for example `totp`, under `auth_mfa_modules` in `configuration.yaml` and restart Home Assistant.

## Warden won't load

Warden writes its groups through Home Assistant's internal auth store. It checks that store on startup and refuses to load, with the error "This Home Assistant version's auth store is not supported", if it has changed. Check that your Home Assistant version is supported and look for a newer Warden release. See [Compatibility](compatibility.md).

## An administrator isn't restricted

Home Assistant administrators keep full access. Turn off **Administrator** for the person under **Settings → People**. See [Groups and permissions](permissions.md#administrators).

## A person can see names but not states

Registry listings (device, area and entity names) aren't covered by Home Assistant's permission checks. See [How it works](how-it-works.md#what-is-not-covered).

## A person is stuck on the profile page

They have required 2FA, and their grace period is over. They need to set it up from their profile. Access comes back as soon as they enroll.

## Reporting a problem

Open an [issue](https://github.com/raine-works/ha-warden/issues) with your Home Assistant version, what the affected user's groups allow, and any relevant Home Assistant logs.
