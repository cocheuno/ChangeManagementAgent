# Setup Guide: ServiceNow PDI, xAI API and Windows 11 Workstation

This guide records every setup step this project took before Grok Build started writing code. Follow it in order to reproduce the environment, including for a new project such as the Problem Management agents. Each step lists the exact commands or clicks and the result you should see.

The prompts used with Grok Build are in [`prompts/`](../../prompts/README.md).

---

## How to use this guide

- **Shell:** all commands are PowerShell, on Windows 11. Use **PowerShell 7** (`pwsh`) once it is installed in Part C. Every command also works in the built-in Windows PowerShell 5.1, except where a step says otherwise.
- **Copy only the command lines.** Use the copy button on a code block. Never copy the prompt text (`PS C:\Users\...>`) or output lines from your terminal. `PS` is a PowerShell alias for `Get-Process`, so a pasted prompt turns your line into a different command (see Part I, row 4).
- **One command per line.** If you put two commands on one line, separate them with `;`.
- **Placeholders:** `devNNNNN` means your instance name, for example `dev181865`. Values in `.env` never take quotes or angle brackets.
- **Secrets:** never paste a password, API key, or any output that contains one into a chat, a prompt, or a commit. Part J covers what to do if one leaks.

---

## Project record

These are the values this project actually used. Your own instance will differ.

| Item | Value |
|---|---|
| PDI URL | `https://dev181865.service-now.com` |
| PDI release | Australia, patch 3. `glide.war` = `glide-australia-02-11-2026__patch3-05-25-2026_06-12-2026_1106.zip`. The properties `glide.buildname` and `glide.buildtag` do not exist on this release. |
| Basic authentication restriction | `glide.authenticate.basic_auth.restriction.active` = true; `...restriction.enforce` = true; `...restriction.enforcement_date` = 2026-10-21 19:46:01 (instance time) |
| Exception role on `admin` | `snc_basic_auth_api_access`, granted 2026-10-21 (Part B5) |
| Admin password | Changed inside the instance with **Set Password** on 2026-10-21 (Part B2). The developer portal's copy is out of date. |
| Outbound email | Off: `glide.email.smtp.active` = false, and no active email account |
| Plugins activated | None. No plugin here provides `rm_release`, so releases are normal changes (Part B7). |
| Missing standard incident fields | `incident.caused_by`, `incident.rfc` and `incident.problem_id` don't exist, although Problem Management is active (Part B8) |
| Custom fields | `incident.u_caused_by` (label "Caused by Change", reference to `change_request`), created by hand on 2026-10-29 (Part B8) |
| Integration user | `syn.svc.change_agents`, created by `seed` in Phase 1 with **Web service access only** |
| GitHub repository | `cocheuno/ChangeManagementAgent`. Branches: `main` (default), `grok-build` (Grok Build's work), `claude/kind-wozniak-yxtiaz` (where the prompts and these docs were written) |
| Workstation | Windows 11, Python 3.12.6, uv 0.9.30 |
| Repository location | `%OneDrive%\Data\Whitewater\Fall 2026\ITSCM 451Z\ChangeManagementAgent`, shared by two PCs (`caronet` and `tcaro`) that are used one at a time. Cloned there from GitHub (D2, option B). |
| Grok Build progress | Phase 0 done and accepted, committed as `e7b0c6a` on `grok-build`. Findings are in `docs/DISCOVERY.md` and `docs/ASSUMPTIONS.md` on that branch. |

---

## Part A: Accounts you need

| Account | Where | Used for |
|---|---|---|
| ServiceNow developer account | https://developer.servicenow.com | Requesting and waking the PDI |
| xAI account, with API credits | https://console.x.ai | The `XAI_API_KEY` the agents use at runtime. This is separate from Grok Build access. |
| Grok Build access | xAI | The coding agent that builds the project |
| GitHub account, with access to the repository | https://github.com | Cloning, pushing, and Git Credential Manager sign-in |
| Microsoft account with OneDrive (only if the repository lives in OneDrive) | OneDrive desktop app, signed in on every PC | Sharing one working folder between PCs |

---

## Part B: ServiceNow PDI

### B1. Request the instance
1. Sign in at https://developer.servicenow.com.
2. Request a Personal Developer Instance. The button label changes from time to time, for example **Request Instance** or **Start Building**. Pick the newest release offered. This project uses Australia.
3. Write down the instance URL: `https://devNNNNN.service-now.com`.
4. **Keep it awake.** A PDI hibernates when idle and is reclaimed after a longer period of inactivity. Check the developer portal for the current rules. Before working, wake the instance from the portal and wait until it opens in the browser. Waking can take several minutes.

### B2. Set a known admin password inside the instance
**Why:** the developer portal signs you in to the instance automatically, so you may never see the instance's own `admin` password. Your developer-portal password and the instance `admin` password are different. The portal's **Manage instance password** option was not available when this project needed it, so set the password inside the instance instead.

1. Open the instance from the portal. You are signed in as `admin`.
2. Open this URL, replacing `devNNNNN`:
   `https://devNNNNN.service-now.com/sys_user_list.do?sysparm_query=user_name%3Dadmin`
3. Click **System Administrator** (User ID `admin`).
4. Click **Set Password**. It is either a button at the top of the form or under **Related Links** at the bottom.
5. Type a new password, or click **Generate**, then click **Save Password**.
   - Use only plain keyboard characters (printable ASCII) with no spaces. Accented letters and symbols such as `£` can break API sign-in even when the password is correct.
   - Don't reuse a password from anywhere else. Store it in a password manager.
6. On the user form, check that **Password needs reset** and **Locked out** are both **unchecked**. If you had to change either one, click **Update**.
7. **Check:** open a private browser window, go to `https://devNNNNN.service-now.com/login.do`, and sign in as `admin` with the new password.
   **Expected:** you reach the instance home page, and it does not ask you to change the password. If it does ask, change it and use the newer password from here on.

### B3. Confirm outbound email is off
1. Open `https://devNNNNN.service-now.com/sys_properties_list.do?sysparm_query=name%3Dglide.email.smtp.active`
2. **Expected:** the value is `false`. This project found `false`, with no active email account, and changed nothing.
3. If the value is `true`, the synthetic users could be sent real email. Decide and record whether to set it to `false` before loading any data.

### B4. Check the basic authentication restriction
Newer releases can enforce a **basic authentication restriction**. While it is enforcing, the REST API returns **401 Unauthorized** to a correct username and password unless the account meets one of these conditions:
- it is marked **Web service access only**;
- it presents an MFA one-time code;
- it holds the role `snc_basic_auth_api_access`.

1. Open `https://devNNNNN.service-now.com/sys_properties_list.do?sysparm_query=nameLIKEbasic_auth.restriction`
2. Read the four properties. This project saw:

   | Property | Value |
   |---|---|
   | `glide.authenticate.basic_auth.restriction.active` | true |
   | `glide.authenticate.basic_auth.restriction.default_decision` | (a choice-list property) |
   | `glide.authenticate.basic_auth.restriction.enforce` | true |
   | `glide.authenticate.basic_auth.restriction.enforcement_date` | 2026-10-21 19:46:01 |

3. If `active` and `enforce` are both `true`, do B5. **Do not edit these properties to switch the restriction off.** Granting the role in B5 affects only one account. Switching the restriction off weakens the whole instance.

### B5. Give `admin` the exception role
1. Open `https://devNNNNN.service-now.com/sys_user_list.do?sysparm_query=user_name%3Dadmin` and click **System Administrator**.
2. Scroll to the **Roles** tab at the bottom of the form and click **Edit...**.
3. In the left-hand list, search for `snc_basic_auth_api_access`. Select it, move it to the right-hand list with the **>** arrow, and click **Save**.
4. **Check:** Part G3. **Expected:** HTTP `200`.

Only the setup commands (`doctor`, `discover`, `seed`, `teardown`) and test helpers use `admin`. The agents run as the integration user, which `seed` creates in Phase 1 with **Web service access only** checked. That passes the restriction and keeps the integration user out of the UI.

### B6. Wake-up and availability checks
| What you see | Meaning | What to do |
|---|---|---|
| An HTML page instead of JSON | The instance is hibernating | Wake it from the developer portal and wait until it opens in the browser |
| `500 Internal Server Error` mentioning `snow_adc` | ServiceNow's load balancer answered because the instance is waking, upgrading or unavailable | Check the instance status on the portal. Wait for **Online**, sign in in the browser, then retry |

### B7. Plugins
No plugin has been activated.
- **Releases:** Phase 1 found that no plugin on this instance provides `rm_release`. The plugins that are present (`com.glide.releaseops`, `com.glide.releaseopsglobal`, `com.snc.release_management_read_roles`) don't create it. Each release is therefore a normal change named `SYN RELEASE <service> <version>`, and its member changes point to it through `parent`. The decision is in message 3 of [`prompts/grok-build-session-messages.md`](../../prompts/grok-build-session-messages.md).
- **The rule:** you activate any plugin yourself; Grok Build never does. If you activate one, record its name, its ID and the date in the project record above.

### B8. Add the "Caused by Change" field to incidents (done 2026-10-29)
**Why:** this instance's incident table has none of the usual links to changes and problems: no `caused_by` (Caused by Change), no `rfc` (Change Request) and no `problem_id` (Problem). That's true even though the Problem Management plugin is active. This project needs "the change that caused this incident" for its change failure rate metric and for scenario S07. That makes it a human-approved customization, like the role in B5.

1. **Confirm the fields are missing.** Signed in as `admin`, open:
   `https://devNNNNN.service-now.com/sys_dictionary_list.do?sysparm_query=elementINcaused_by,rfc,problem_id`
   On a typical instance this lists Caused by Change, Change Request and Problem on the incident table. This instance listed none of them.
2. **Check whether Problem Management is active:**
   `https://devNNNNN.service-now.com/v_plugin_list.do?sysparm_query=nameLIKEproblem`
   On this instance it is active.
3. **Create the field:**
   1. Go to **All → System Definition → Tables**, search for `incident`, and open **Incident**.
   2. On the **Columns** tab, click **New**.
   3. Set **Type** to `Reference` and **Column label** to `Caused by Change`.
   4. Set **Column name** to exactly `u_caused_by`. ServiceNow fills in `u_caused_by_change` from the label, so overwrite it.
   5. On the **Reference Specification** tab, set **Reference** to `Change Request`.
   6. Click **Submit**.
4. **Check it:**
   `https://devNNNNN.service-now.com/sys_dictionary_list.do?sysparm_query=element%3Du_caused_by`
   **Expected:** one row on `incident`, of type Reference, pointing to `change_request`.

The agents and metrics use `incident.u_caused_by` wherever the master prompt says `caused_by`; `docs/ASSUMPTIONS.md` records the mapping. `teardown` clears the values along with the synthetic incidents but leaves the field, because the API refuses to delete fields. To remove the field, delete its dictionary entry in the UI as `admin`.

---

## Part C: Workstation (do this on every PC)

### C1. Install the tools
Open PowerShell and run each line:
```powershell
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
winget install --id Microsoft.PowerShell -e --accept-source-agreements --accept-package-agreements
winget install --id Microsoft.VisualStudioCode -e --accept-source-agreements --accept-package-agreements
```
VS Code is optional, but it is a convenient editor for `.env`. Install Grok Build using xAI's instructions for Windows.

### C2. Switch to PowerShell 7 and allow local scripts
Close every PowerShell window. Open **PowerShell 7** (search Start for "PowerShell 7", or run `pwsh`). Then run:
```powershell
git --version
python --version
uv --version
$PSVersionTable.PSVersion
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
**Expected:** a Git version, Python `3.12.x`, a uv version, and a PowerShell version of `7.x`.

PowerShell 7 matters for two reasons:
- Windows PowerShell 5.1 does not accept `&&`.
- In 5.1, `echo ... > file` and `>>` write UTF-16 files that Git and Python misread.

### C3. Git identity
```powershell
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```
The first clone or push opens a browser sign-in for GitHub. That is Git Credential Manager, which comes with Git for Windows.

### C4. Keep the virtual environment out of OneDrive
Skip this step if the repository is not in OneDrive.

**Why:**
- A Python virtual environment holds thousands of files and absolute paths to one PC's user folder. The two PCs in this project have different user folders (`C:\Users\caronet` and `C:\Users\tcaro`).
- A virtual environment synced through OneDrive breaks on the other PC and causes sync conflicts.
- uv lets you put it elsewhere through the `UV_PROJECT_ENVIRONMENT` environment variable.

**Default: set it per session.** This affects only this project. Run it every time you open a terminal for this project, before any `uv` command and before starting Grok Build from that terminal:
```powershell
Set-Location (Join-Path $env:OneDrive 'Data\Whitewater\Fall 2026\ITSCM 451Z\ChangeManagementAgent')
$env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'
```
Change the quoted folder if your repository is elsewhere in OneDrive (D2).

**Alternative: set it once per PC.** Use this only if **no other project** on the PC uses uv. Every uv project on that PC would share this one environment and overwrite each other's packages.
```powershell
[Environment]::SetEnvironmentVariable('UV_PROJECT_ENVIRONMENT', (Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'), 'User')
```
Open a new terminal afterwards.

**Check:** `$env:UV_PROJECT_ENVIRONMENT` prints a path under `AppData\Local\venvs\ChangeManagementAgent`.

Grok Build's session messages also tell it to set this variable in its own commands (message 3 in `prompts/grok-build-session-messages.md`), so a `.venv` never appears inside the repository.

---

## Part D: Repository

### D1. One-time GitHub setup (already done for this project; recorded here)
The repository started with only the prompt branch. These commands made `main` the base and kept `.env` out of Git.
```powershell
git clone https://github.com/cocheuno/ChangeManagementAgent.git
Set-Location .\ChangeManagementAgent
git checkout -b main
git push -u origin main
Add-Content -Path .gitignore -Value '.env'
git add .gitignore
git commit -m "Ignore .env"
git push
git checkout -b grok-build
```
Then, on GitHub: **Settings → General → Default branch**, click the switch-branch icon, choose `main`, click **Update**, and confirm.

`Add-Content` is used on purpose. In Windows PowerShell 5.1, `echo ".env" >> .gitignore` writes a UTF-16 file that Git misreads, so `.env` would not be ignored.

### D2. Put the repository in OneDrive (this project's setup)
**Choose the OneDrive folder first.** This project uses `OneDrive\Data\Whitewater\Fall 2026\ITSCM 451Z\ChangeManagementAgent`. Set it in each new terminal, changing the quoted part if you use a different folder:
```powershell
$repo = Join-Path $env:OneDrive 'Data\Whitewater\Fall 2026\ITSCM 451Z\ChangeManagementAgent'
$env:OneDrive
$repo
```
**Expected:** `$env:OneDrive` prints your OneDrive folder; if it prints nothing, sign in to the OneDrive app. The path contains spaces, so always keep `"$repo"` in quotes.

Then use **one** of the two options below, on **one** PC only. OneDrive copies the result to the other PC.

#### Option A: move an existing local copy into OneDrive
Use this when the local copy holds work that isn't on GitHub yet.
1. Close Grok Build, VS Code, and every other terminal using the folder.
2. Check that everything is pushed, then remove the per-PC virtual environment:
   ```powershell
   $src = "$HOME\ITSCM451\ChangeManagementAgent"
   Set-Location "$src"
   git remote get-url origin
   git fetch origin
   git status
   git push -u origin grok-build
   if (Test-Path .venv) { Remove-Item .venv -Recurse -Force }
   ```
   **Expected:** the URL ends in `ChangeManagementAgent.git`; `git status` shows `nothing to commit, working tree clean`; the push succeeds or says `Everything up-to-date`. If `git status` lists changes, stop and decide what to do with them first.
3. Move the folder:
   ```powershell
   Set-Location $HOME
   New-Item -ItemType Directory -Force -Path (Split-Path "$repo") | Out-Null
   Move-Item -Path "$src" -Destination "$repo"
   Set-Location "$repo"
   git status
   ```
   **Expected:** a clean tree on `grok-build`.

#### Option B: clone straight into OneDrive (what this project did)
Use this when everything is already on GitHub. The only thing to carry over is `.env`. This project did this on the `caronet` PC, whose old clone at `$HOME\ITSCM451\ChangeManagementAgent` had an out-of-date `.env`.
1. Clone the working branch:
   ```powershell
   Test-Path "$repo"
   git clone -b grok-build https://github.com/cocheuno/ChangeManagementAgent.git "$repo"
   Set-Location "$repo"
   git log --oneline -1
   ```
   **Expected:** `Test-Path` prints `False` (the folder must not exist yet), the clone succeeds, and the last line shows the latest `grok-build` commit.
2. Bring in `.env`. If an old local clone has one, copy it and then correct it:
   ```powershell
   $old = "$HOME\ITSCM451\ChangeManagementAgent"
   Test-Path "$old\.env"
   Copy-Item "$old\.env" "$repo\.env"
   notepad .env
   ```
   In Notepad, set `SN_ADMIN_PASSWORD` to the **current** admin password from B2, and check every line against F2: no quotes, no trailing `/`, all seven names. If there is no old `.env`, create one with F1 and F2 instead.
3. Check it, then retire the old clone so nobody uses it by mistake:
   ```powershell
   git check-ignore .env
   Rename-Item "$old" ChangeManagementAgent-old
   ```
   `git check-ignore` must print `.env`. Run the F5 checks.

#### After either option
1. In File Explorer, right-click the `ChangeManagementAgent` folder in OneDrive and choose **Always keep on this device**.
2. Recreate the environment outside OneDrive and run the checks. Wake the PDI first.
   ```powershell
   Set-Location "$repo"
   $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA 'venvs\ChangeManagementAgent'
   git status
   uv sync
   uv run pytest
   uv run ruff check .
   uv run cm-agents doctor
   Test-Path .venv
   ```
   **Expected:**
   - `pytest` passes; Phase 0 had 51 tests;
   - `ruff` reports no problems;
   - `doctor` reports the admin login as OK; until Phase 1 it ends with `agent user missing: run seed`;
   - `Test-Path .venv` prints `False`.
3. Run the xAI test (G2).
4. Wait for OneDrive's green check before switching PCs.

**On the other PC:**
1. Wait for OneDrive to finish syncing the folder, then choose **Always keep on this device** on it.
2. Do Part C if it hasn't been done on that PC.
3. If that PC has an old local clone, rename it: `Rename-Item "$HOME\ITSCM451\ChangeManagementAgent" ChangeManagementAgent-old`. Don't move it; the OneDrive copy replaces it.
4. Set `$repo` as above and run step 2 of "After either option". Each PC builds its own environment under its own `AppData\Local`.

### D3. Rules for OneDrive plus Git
- **One PC at a time.** Before switching, close Grok Build and the terminals, and wait for OneDrive's green check. Two PCs writing to `.git` or to the SQLite checkpoint database at the same time can corrupt them.
- **OneDrive is not version control.** Keep pushing to GitHub after reviewing each phase. GitHub is the backup and the record.
- **OneDrive does carry what GitHub doesn't:** `.env`, `data/synthetic/` (including `manifest.json`, which `teardown` needs), `var/` (paused workflows and simulator state) and `reports/`. That's why both PCs can run `seed`, `teardown` and the scenarios.
- **OneDrive uploads `.env` to your Microsoft account.** Accept that, or keep the repository out of OneDrive.

### D4. Bring in updates to the prompts and docs
These files are written on the `claude/kind-wozniak-yxtiaz` branch. To merge them into Grok Build's branch:
```powershell
git remote get-url origin
git checkout grok-build
git fetch origin
git merge --no-edit origin/claude/kind-wozniak-yxtiaz
git push
```
- **Check the URL first.** The first command must print a URL ending in `ChangeManagementAgent.git`. If it doesn't, you're in another repository: stop, and `Set-Location` to the right folder.
- **`--no-edit`** stops Git from opening a text editor for the merge message. On Windows that editor is often Vim.
- **Do this only while Grok Build is stopped** between phases. Git refuses to merge over uncommitted changes, but waiting avoids the problem altogether.

### D5. Branch roles
| Branch | Role | Who writes to it |
|---|---|---|
| `main` | **Default branch.** Holds only accepted phases; this is what the student and other readers see | Fast-forwarded from `grok-build` after each accepted phase |
| `grok-build` | Grok Build's working branch. Phases are committed here and pushed after review | Grok Build commits; you push |
| `claude/kind-wozniak-yxtiaz` | Where the prompts and these docs are written | Merged into `grok-build` with D4 |

After you accept each phase:
```powershell
git push
git push origin grok-build:main
```
The second command succeeds only if `main` can fast-forward, so it never overwrites anything on `main`. If it's rejected, someone committed to `main` directly; stop and look before doing anything else.

**Check the default branch once:** on GitHub, open **Settings → General → Default branch**. It must say `main`. If it doesn't, click the switch-branch icon, choose `main`, click **Update**, and confirm.

---

## Part E: xAI API key and model

### E1. Credits
1. Sign in at https://console.x.ai. Create a team when asked.
2. On the **Billing** page, add a payment method and buy credits. The API is prepaid and refuses calls until the team has credits. Grok Build access does not necessarily include API credits.

### E2. Create the key
1. Open the **API Keys** page and click **Create**. The labels may differ slightly.
2. **Name:** for example `change-agents-pdi`.
3. **Endpoints:** allow only chat completions and the model list.
4. **Models:** allow only the models you will use. If you switch models later, update the key's permissions.
5. Copy the key with the console's copy button. It may be shown only once. Paste it straight into `.env` (Part F).

### E3. Choose the model
- List the models your key can use with Part G1. Pick from that list rather than from articles, which disagree about which Grok model is newest.
- The agents mostly fill in structured fields, run checklists, and write short documents. Start with a cheaper general model, and confirm that it supports tool calling and structured outputs.
- Don't use coding models such as `grok-build-0.1`, or the "Fast" variants that are available only inside Grok Build or Cursor.
- The Phase 2 gate checks the choice: the plan-quality checklist must agree with the synthetic labels at least 90% of the time. If it falls short, switch `XAI_MODEL` to a stronger model and run the gate again.

---

## Part F: The `.env` file

### F1. Create it
In the repository root:
```powershell
New-Item -Path .env -ItemType File
notepad .env
```
Creating the empty file first stops Notepad from saving it as `.env.txt`. Notepad on Windows 11 saves UTF-8 by default.

### F2. Contents
Write one line per setting, in the form `NAME=value`. No quotes, no angle brackets, and no spaces around `=`.
```
SN_INSTANCE_URL=https://devNNNNN.service-now.com
SN_ADMIN_USER=admin
SN_ADMIN_PASSWORD=the admin password from B2
SN_AGENT_USER=syn.svc.change_agents
SN_AGENT_PASSWORD=a strong password you make up; seed sets it on the integration user
XAI_API_KEY=the key from E2, which starts with xai-
XAI_MODEL=a model ID from G1
```
Rules:
- `SN_INSTANCE_URL` has **no trailing `/`**. The project rejects any URL that doesn't end in `.service-now.com`.
- Each name appears once. Delete old lines when you change a value. The helper in F4 reads the first matching line.
- `SN_AGENT_USER` does not exist in ServiceNow until Phase 1 `seed` creates it.

### F3. Confirm Git ignores it
```powershell
git check-ignore .env
git status
```
**Expected:** the first command prints `.env`, and `git status` does not list `.env`.

### F4. Helper to read values without printing them
Run this once in every new PowerShell window:
```powershell
function EnvVal($name) { (Select-String -Path .env -Pattern "^$name=(.*)$").Matches[0].Groups[1].Value.Trim() }
```
Always pass the setting's **name**, never its value:
```powershell
$sn = EnvVal 'SN_INSTANCE_URL'
```
Passing a value, as in `EnvVal 'https://...'`, finds no line and fails with `Cannot index into a null array`.

### F5. Check values without showing them
```powershell
Get-Content .env | ForEach-Object { ($_ -split '=',2)[0] }

$k = EnvVal 'XAI_API_KEY'
$k.Length
$k.StartsWith('xai-')
$k -match '[^\x21-\x7E]'

EnvVal 'SN_ADMIN_USER'
EnvVal 'SN_INSTANCE_URL'
$p = EnvVal 'SN_ADMIN_PASSWORD'
$p -match '^["'']|["'']$'
$p -match '[^\x21-\x7E]'
(Select-String -Path .env -Pattern '^SN_ADMIN_PASSWORD=').Count
```
**Expected:**
- the first command lists the seven names;
- the key's length is a number, `StartsWith` is `True`, and the hidden-character check is `False`;
- the username prints as `admin`, and the URL has no trailing `/`;
- both password checks are `False`, and the count is `1`.

To check that `.env` holds the same password the browser accepts, without displaying it:
```powershell
$typed = Read-Host -AsSecureString "Type the admin password you used in the browser"
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($typed))
$plain -ceq (EnvVal 'SN_ADMIN_PASSWORD')
Remove-Variable plain, typed
```
**Expected:** `True`.

---

## Part G: Connection tests
Run these from the repository root after F4. Each one prints only a status, a list or a short reply, never a secret.

### G1. List the xAI models
```powershell
$headers = @{ Authorization = "Bearer $(EnvVal 'XAI_API_KEY')" }
(Invoke-RestMethod -Uri https://api.x.ai/v1/models -Headers $headers).data | Select-Object id
```
**Expected:** a list of model IDs.

### G2. Test the chosen xAI model
```powershell
$body = @{ model = (EnvVal 'XAI_MODEL'); messages = @(@{ role = "user"; content = "Reply with OK" }) } | ConvertTo-Json -Depth 5
(Invoke-RestMethod -Uri https://api.x.ai/v1/chat/completions -Method Post -Headers $headers -ContentType "application/json" -Body $body).choices[0].message.content
```
**Expected:** `OK`.

### G3. Test the PDI login directly
This skips `.env`. curl asks for the password and hides what you type:
```powershell
curl.exe -s -o NUL -w "%{http_code}`n" -u admin -H "Accept: application/json" "https://devNNNNN.service-now.com/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=user_name"
```
**Expected:** `200`.

### G4. Test the PDI login from `.env`
```powershell
$sn = EnvVal 'SN_INSTANCE_URL'
$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$(EnvVal 'SN_ADMIN_USER'):$(EnvVal 'SN_ADMIN_PASSWORD')"))
$snHeaders = @{ Authorization = "Basic $basic"; Accept = "application/json" }
(Invoke-RestMethod -Uri "$sn/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=user_name" -Headers $snHeaders).result
```
**Expected:** one `user_name` line.

**Never print `$basic` or `$snHeaders`.** `$basic` is your username and password in Base64, which anyone can decode.

After changing `.env`, rebuild `$headers`, `$basic` and `$snHeaders`. They keep the values they had when you created them.

---

## Part H: Start Grok Build
1. Open a PowerShell 7 window. Run the C4 per-session line and the F4 helper.
2. Start Grok Build in the repository folder.
3. Send the messages in [`prompts/grok-build-session-messages.md`](../../prompts/grok-build-session-messages.md), in order:
   - message 1 starts the project;
   - message 2 answers Grok's questions before Phase 0;
   - message 3 starts Phase 1 in a new session with the Phase 0 decisions;
   - after each phase, use the review checklist and reply template in that file.
4. Grok Build commits each phase locally and stops. Review the phase report, then push:
   ```powershell
   git push
   ```

---

## Part I: Troubleshooting (every error this project hit)

| # | Error or symptom | Cause | Fix |
|---|---|---|---|
| 1 | `Unexpected token '(' in expression or statement` | Two commands pasted onto one line | Put each command on its own line, or separate them with `;` |
| 2 | xAI: `Incorrect API key provided` | Quotes, brackets or a leftover placeholder around the key in `.env`. Or `$headers` was built before `EnvVal` existed, or before `.env` was fixed | Run the F5 checks. Remove quotes and brackets. Rebuild `$headers`. If the checks pass, create a new key (E2) |
| 3 | `Cannot index into a null array` | `EnvVal` was given a value instead of a name, or that name isn't in `.env`, or you're in the wrong folder | Use `EnvVal 'SETTING_NAME'`. Check the line in `.env`. Check `Get-Location` |
| 4 | `Get-Process : A positional parameter cannot be found that accepts argument ...` | The pasted line included the prompt text `PS C:\...>`. `PS` means `Get-Process`. **This can print your secrets in the error.** | Copy only the command lines from a code block. If a secret appeared in the error, follow Part J |
| 5 | `The term 'https://...' is not recognized as the name of a cmdlet` | An output line or a URL was pasted as if it were a command | Paste only command lines |
| 6 | PDI: `(401) Unauthorized` with a wrong or unknown password | The developer-portal password was used instead of the instance `admin` password | Set the password inside the instance (B2), update `.env`, rebuild the headers |
| 7 | PDI: `(401) Unauthorized` even though the browser sign-in works | The basic authentication restriction is enforcing (B4) | Grant `snc_basic_auth_api_access` to `admin` (B5) |
| 8 | PDI: `(401)` and the browser asks for a password change | **Password needs reset** is set | Change the password, update `.env`, and make sure the box is unchecked |
| 9 | PDI: `500 Internal Server Error` mentioning `snow_adc` | The instance is waking, upgrading or unavailable | B6 |
| 10 | PDI: HTML instead of JSON | The instance is hibernating | Wake it from the developer portal |
| 11 | `The token '&&' is not a valid statement separator` | Windows PowerShell 5.1 | Use PowerShell 7, or run the commands on separate lines |
| 12 | `.env` committed despite `.gitignore`, or Python can't read `.env` | The file was written with `echo` or `>>` in PowerShell 5.1, which saves UTF-16 | Recreate `.gitignore` with `Add-Content` (D1) and `.env` with Notepad (F1) |
| 13 | File saved as `.env.txt` | Notepad added `.txt` | Create the file first with `New-Item` (F1). In Notepad's Save dialog, choose **All files** |
| 14 | `running scripts is disabled on this system` | The execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 15 | The developer portal has no **Manage instance password** option | The portal layout changed, or the option is temporarily unavailable | Set the password inside the instance (B2) |
| 16 | `pathspec 'grok-build' did not match`, or `'origin/claude/...' - not something we can merge`, while in another project's folder | The git commands ran in the wrong repository (this happened in a different OneDrive project) | Nothing to undo: those commands fail without changing anything, and `git fetch` only refreshes Git's reference copy of GitHub. Run `git remote get-url origin` before git commands. |
| 17 | `Set-Location : Cannot find path ...`, then `fatal: not a git repository` | `$src` was changed to the new OneDrive path, or this PC doesn't hold the copy you meant to move | `$src` is where the repository is **now**; only `$repo` is the new location. If the copy with the latest work is on the other PC and everything is pushed, use D2 option B on this PC instead |

---

## Part J: Security

- **What counts as a secret:** `SN_ADMIN_PASSWORD`, `SN_AGENT_PASSWORD`, `XAI_API_KEY`, and anything built from them, such as `$basic` or an `Authorization` header. Base64 is not encryption.
- **Where secrets live:** only in `.env`, which Git ignores. Never put them in prompts, chats, code, commits or screenshots.
- **Check that Git history has never held `.env`:**
  ```powershell
  git log --all --oneline -- .env
  ```
  **Expected:** no output.
- **If a ServiceNow password leaks:** change it inside the instance (B2). Update `.env` on every PC, which with OneDrive means one file. Rebuild the headers.
- **If the xAI key leaks:** on **API Keys** in the console, delete the key, then create a new one (E2). Update `.env`.
- **If a secret was pushed to GitHub:** rotate it at once. Deleting the commit isn't enough once it has been pushed.
- **This project's incident:** on 2026-10-21 a pasted `PS C:\...>` prompt printed the Base64 admin credential (Part I, row 4). The password was changed with **Set Password** the same day.
- **Account scope:** `admin` is used only for setup commands and test helpers. The agents run as `syn.svc.change_agents`, which has **Web service access only** and only the roles Phase 1 shows are needed.
