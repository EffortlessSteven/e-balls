//! Count full raw Git commit messages by UTC committer day.
//! The rasterizer remains src/bin/e-balls.rs; this binary supplies measured rows
//! and (when requested) the actual top contributor's linked GitHub avatar.
use anyhow::{anyhow, bail, Context, Result};
use chrono::{DateTime, Datelike, Duration as DateDuration, NaiveDate, Utc};
use clap::Parser;
use reqwest::blocking::Client;
use reqwest::redirect::Policy;
use ring::digest::{digest, SHA256};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const MAX_DAYS: i64 = 366;
const MAX_OBJECT: usize = 32 * 1024 * 1024;

#[derive(Parser)]
#[command(version, about = "Count letters in commit messages and select the top contributor")]
struct Args {
    #[arg(long)]
    repo: PathBuf,
    #[arg(long, default_value = "HEAD")]
    r#ref: String,
    /// Owner/repo for GitHub attribution and optional avatar lookup.
    #[arg(long)]
    repository: String,
    #[arg(long, default_value = "perl-lsp")]
    project: String,
    #[arg(long, default_value = "e")]
    letter: String,
    #[arg(long, conflicts_with_all = ["days", "start"])]
    since: Option<String>,
    #[arg(long, conflicts_with = "start")]
    days: Option<i64>,
    #[arg(long)]
    start: Option<NaiveDate>,
    /// Exclusive UTC date (defaults to today).
    #[arg(long)]
    end: Option<NaiveDate>,
    #[arg(long)]
    out: PathBuf,
    /// Resolve the winning author to a GitHub account and write the real avatar.
    /// Without this flag, collection is offline and does not call GitHub.
    #[arg(long)]
    avatar_out: Option<PathBuf>,
}

#[derive(Clone, Debug)]
struct Author {
    key: String,
    name: String,
    count: u64,
    commits: u64,
    shas: Vec<String>,
    bot: bool,
}

fn sha256(bytes: &[u8]) -> String {
    digest(&SHA256, bytes)
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn is_sha(value: &str) -> bool {
    (value.len() == 40 || value.len() == 64)
        && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn git(repo: &Path, args: &[&str]) -> Result<Vec<u8>> {
    let output = Command::new("git")
        .arg("--no-replace-objects")
        .arg("-C")
        .arg(repo)
        .args(args)
        .output()
        .context("unable to run git")?;
    if !output.status.success() {
        bail!(
            "git {}: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    Ok(output.stdout)
}

fn parse_author(headers: &[u8]) -> Result<(String, String, bool)> {
    let line = headers
        .split(|byte| *byte == b'\n')
        .find(|line| line.starts_with(b"author "))
        .context("commit is missing its author header")?;
    let text = String::from_utf8_lossy(line);
    let left = text.rfind('<').context("author email has no opening bracket")?;
    let right = text[left..]
        .find('>')
        .map(|index| index + left)
        .context("author email has no closing bracket")?;
    let name = text["author ".len()..left].trim().to_owned();
    let email = text[left + 1..right].trim().to_ascii_lowercase();
    if email.is_empty() && name.is_empty() {
        bail!("commit has no author identity");
    }
    // Group only by the recorded Git author identity; never infer that different
    // addresses belong to the same GitHub user.
    let key = if email.is_empty() {
        format!("name:{}", name.to_lowercase())
    } else {
        format!("email:{email}")
    };
    let identity = format!("{name} {email}").to_ascii_lowercase();
    let bot = identity.contains("[bot]")
        || identity.contains("dependabot")
        || identity.contains("renovate[bot]")
        || identity.contains("github-actions");
    Ok((key, name, bot))
}

fn committer_time(headers: &[u8]) -> Result<i64> {
    let line = headers
        .split(|byte| *byte == b'\n')
        .find(|line| line.starts_with(b"committer "))
        .context("commit is missing its committer header")?;
    let text = String::from_utf8_lossy(line);
    text.split_ascii_whitespace()
        .rev()
        .nth(1)
        .context("committer has no UTC epoch")?
        .parse::<i64>()
        .context("invalid committer UTC epoch")
}

fn count_ascii(message: &[u8], letter: u8) -> u64 {
    message
        .iter()
        .filter(|byte| byte.to_ascii_lowercase() == letter)
        .count() as u64
}

fn ranked_authors(authors: BTreeMap<String, Author>) -> Vec<Author> {
    let mut ranked: Vec<_> = authors.into_values().filter(|author| !author.bot).collect();
    ranked.sort_by(|a, b| {
        b.count
            .cmp(&a.count)
            .then_with(|| b.commits.cmp(&a.commits))
            .then_with(|| a.key.cmp(&b.key))
    });
    ranked
}

fn validate_repository(repository: &str) -> Result<()> {
    let Some((owner, name)) = repository.split_once('/') else {
        bail!("repository must be owner/name");
    };
    if name.contains('/')
        || [owner, name].iter().any(|value| {
            value.is_empty()
                || !value
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        })
    {
        bail!("repository must be owner/name");
    }
    Ok(())
}

fn count(
    repo: &Path,
    reference: &str,
    repository: &str,
    project: &str,
    start: NaiveDate,
    end: NaiveDate,
    letter: u8,
) -> Result<(Value, Vec<Author>)> {
    validate_repository(repository)?;
    if project.is_empty() || project.len() > 80 || project.chars().any(char::is_control) {
        bail!("project must be a single-line name of at most 80 characters");
    }
    let number_of_days = (end - start).num_days();
    if !(1..=MAX_DAYS).contains(&number_of_days) {
        bail!("window must cover between 1 and {MAX_DAYS} complete UTC days");
    }
    if git(repo, &["rev-parse", "--is-shallow-repository"])?.trim_ascii() != b"false" {
        bail!("shallow history cannot produce complete counts; fetch full ancestry");
    }
    let pin = String::from_utf8(
        git(repo, &["rev-parse", "--verify", "--end-of-options", &format!("{reference}^{{commit}}")])?,
    )?
    .trim()
    .to_owned();
    if !is_sha(&pin) {
        bail!("Git did not resolve ref to a complete commit SHA");
    }
    let beginning = start
        .and_hms_opt(0, 0, 0)
        .context("bad start date")?
        .and_utc()
        .timestamp();
    let ending = end
        .and_hms_opt(0, 0, 0)
        .context("bad end date")?
        .and_utc()
        .timestamp();

    // Read all reachable ancestry before filtering. --since/--until on rev-list
    // can prune behind an older-dated parent and miss newer-dated ancestors.
    let revisions = git(repo, &["rev-list", "--timestamp", &pin, "--"])?;
    let mut unique = BTreeSet::new();
    let mut selected = Vec::<(i64, String)>::new();
    for line in revisions.split(|byte| *byte == b'\n').filter(|line| !line.is_empty()) {
        let text = std::str::from_utf8(line).context("non-UTF-8 rev-list output")?;
        let Some((timestamp, sha)) = text.split_once(' ') else {
            bail!("invalid rev-list output");
        };
        let timestamp: i64 = timestamp.parse().context("invalid revision time")?;
        if !is_sha(sha) {
            bail!("invalid Git commit SHA");
        }
        if beginning <= timestamp && timestamp < ending && unique.insert(sha.to_owned()) {
            selected.push((timestamp, sha.to_owned()));
        }
    }
    selected.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));

    let mut buckets: BTreeMap<String, (u64, u64)> = BTreeMap::new();
    for day in 0..number_of_days {
        buckets.insert((start + DateDuration::days(day)).to_string(), (0, 0));
    }
    let mut receipts = Vec::with_capacity(selected.len());
    let mut authors = BTreeMap::<String, Author>::new();

    // Stream length-framed Git commit objects, including arbitrary message bytes.
    // Producer and consumer run concurrently to avoid a full pipe deadlock.
    if !selected.is_empty() {
        let mut child = Command::new("git")
            .arg("--no-replace-objects")
            .arg("-C")
            .arg(repo)
            .args(["cat-file", "--batch"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .context("unable to start git cat-file")?;
        let mut stdin = child.stdin.take().context("missing cat-file stdin")?;
        let keys: Vec<String> = selected.iter().map(|(_, sha)| sha.clone()).collect();
        let writer = std::thread::spawn(move || -> std::io::Result<()> {
            for sha in keys {
                stdin.write_all(sha.as_bytes())?;
                stdin.write_all(b"\n")?;
            }
            stdin.flush()?;
            Ok(())
        });
        let mut reader = BufReader::new(child.stdout.take().context("missing cat-file stdout")?);
        let processed = (|| -> Result<()> {
            for (expected_time, expected_sha) in &selected {
                let mut response = String::new();
                if reader.read_line(&mut response)? == 0 {
                    bail!("truncated cat-file object list");
                }
                let mut parts = response.split_ascii_whitespace();
                let sha = parts.next().context("missing cat-file SHA")?;
                let kind = parts.next().context("missing cat-file object type")?;
                let size: usize = parts
                    .next()
                    .context("missing cat-file object size")?
                    .parse()
                    .context("bad cat-file object size")?;
                if sha != expected_sha || kind != "commit" || parts.next().is_some() {
                    bail!("cat-file returned an unexpected object: {sha}");
                }
                if size > MAX_OBJECT {
                    bail!("commit object {sha} exceeds the 32 MiB limit");
                }
                let mut payload = vec![0; size];
                reader.read_exact(&mut payload)?;
                let mut newline = [0; 1];
                reader.read_exact(&mut newline)?;
                if newline[0] != b'\n' {
                    bail!("truncated cat-file framing");
                }
                let Some(delimiter) = payload.windows(2).position(|bytes| bytes == b"\n\n") else {
                    bail!("commit {sha} has no message boundary");
                };
                let headers = &payload[..delimiter];
                let message = &payload[delimiter + 2..];
                let actual_time = committer_time(headers)?;
                if actual_time != *expected_time {
                    bail!("committer timestamp differs from rev-list for {sha}");
                }
                let when = DateTime::<Utc>::from_timestamp(actual_time, 0)
                    .context("timestamp is outside the supported range")?;
                let day = when.date_naive().to_string();
                let value = count_ascii(message, letter);
                let bucket = buckets.get_mut(&day).context("selected commit lies outside window")?;
                bucket.0 = bucket.0.checked_add(value).context("daily count overflow")?;
                bucket.1 += 1;

                let (identity, name, bot) = parse_author(headers)?;
                let author = authors.entry(identity.clone()).or_insert_with(|| Author {
                    key: identity, name, count: 0, commits: 0, shas: Vec::new(), bot,
                });
                author.count = author.count.checked_add(value).context("author count overflow")?;
                author.commits += 1;
                author.shas.push(sha.to_owned());
                receipts.push(json!({
                    "sha": sha,
                    "committed_at": when.format("%Y-%m-%dT%H:%M:%SZ").to_string(),
                    "day": day,
                    "count": value,
                    "message_sha256": sha256(message),
                }));
            }
            Ok(())
        })();
        if processed.is_err() {
            let _ = child.kill();
        }
        let write_result = writer.join().map_err(|_| anyhow!("git stdin writer panicked"))?;
        let status = child.wait()?;
        processed?;
        write_result.context("could not stream selected commit SHAs")?;
        if !status.success() {
            bail!("git cat-file failed with {status}");
        }
    }

    let rows: Vec<Value> = buckets
        .iter()
        .map(|(day, (count, commits))| {
            let date = NaiveDate::parse_from_str(day, "%Y-%m-%d").expect("validated calendar");
            json!({
                "label": date.format("%a %b %d").to_string(),
                "date": day, "count": count, "commits": commits,
            })
        })
        .collect();
    let total_count: u64 = buckets
        .values()
        .try_fold(0_u64, |sum, (count, _)| sum.checked_add(*count))
        .context("total count overflow")?;
    let lower = (letter as char).to_ascii_lowercase();
    let data = json!({
        "schema_version": 1,
        "title": format!("Occurrences of '{lower}' in {project} commit messages"),
        "subtitle": format!("{} to {} · UTC", start, end.pred_opt().context("bad end")?),
        "footer": format!("github.com/{repository}"),
        "unit": format!("{lower}'s"),
        "unit_singular": lower.to_string(),
        "rows": rows,
        "source": {
            "repository": repository,
            "requested_ref": reference,
            "commit": pin,
            "start_inclusive": format!("{start}T00:00:00Z"),
            "end_exclusive": format!("{end}T00:00:00Z"),
            "timestamp": "committer",
            "timezone": "UTC",
            "traversal": "all reachable commits, including merges; each SHA once",
            "message": "full raw commit message, including body and trailers",
            "letter": lower.to_string(),
            "case": "ASCII-insensitive",
            "total_commits": receipts.len(),
            "total_count": total_count,
            "commits": receipts,
        }
    });
    Ok((data, ranked_authors(authors)))
}

fn fetch_bounded(client: &Client, url: &str, token: Option<&str>, limit: u64) -> Result<Vec<u8>> {
    let mut request = client.get(url).header("Accept", "application/vnd.github+json");
    if let Some(token) = token.filter(|token| !token.is_empty()) {
        request = request.bearer_auth(token);
    }
    let response = request.send().with_context(|| format!("HTTP request failed: {url}"))?;
    let status = response.status();
    if !status.is_success() {
        bail!("GitHub response {status} from {url}");
    }
    let mut bytes = Vec::new();
    response.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        bail!("GitHub response exceeds the size limit");
    }
    Ok(bytes)
}

fn fetch_top_avatar(
    repository: &str,
    ranked: &[Author],
    destination: &Path,
) -> Result<Value> {
    let top = ranked.first().context(
        "no non-bot contributor in the selected window; use an explicit avatar input"
    )?;
    let client = Client::builder()
        .user_agent("EffortlessSteven/e-balls")
        .timeout(Duration::from_secs(25))
        .redirect(Policy::none())
        .build()?;
    let token = std::env::var("GITHUB_TOKEN").ok();
    let mut linked = None;
    // The sampled commit must be attributed by GitHub to this same Git author.
    for sha in top.shas.iter().rev().take(10) {
        let url = format!("https://api.github.com/repos/{repository}/commits/{sha}");
        let bytes = fetch_bounded(&client, &url, token.as_deref(), 2_000_000)?;
        let body: Value = serde_json::from_slice(&bytes)?;
        let Some(user) = body.get("author").filter(|value| !value.is_null()) else {
            continue;
        };
        let Some(login) = user.get("login").and_then(Value::as_str) else {
            continue;
        };
        let Some(id) = user.get("id").and_then(Value::as_u64) else {
            continue;
        };
        if user.get("type").and_then(Value::as_str) == Some("Bot")
            || login.to_ascii_lowercase().ends_with("[bot]")
        {
            bail!("top commit author is a GitHub bot; use an explicit avatar input");
        }
        linked = Some((login.to_owned(), id, sha.clone()));
        break;
    }
    let (login, id, sample_sha) = linked.context(
        "top Git author is not associated with a GitHub account; use an explicit avatar input"
    )?;
    // Construct the image URL from an ID returned by GitHub. The API token
    // never accompanies requests to the avatar host.
    let avatar_url = format!("https://avatars.githubusercontent.com/u/{id}?s=512&v=4");
    let bytes = fetch_bounded(&client, &avatar_url, None, 4_000_000)?;
    let image = image::load_from_memory(&bytes)
        .context("GitHub contributor avatar is not a supported image")?
        .to_rgb8();
    if image.width() == 0 || image.height() == 0 || image.width() > 2048 || image.height() > 2048 {
        bail!("GitHub contributor avatar dimensions are invalid");
    }
    let parent = destination.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    image.save_with_format(destination, image::ImageFormat::Png)?;
    let normalized = fs::read(destination)?;
    Ok(json!({
        "login": login,
        "id": id,
        "author_name": top.name,
        "counted_letters": top.count,
        "authored_commits": top.commits,
        "sample_commit": sample_sha,
        "selection": "non-bot Git author with most counted letters; then commits; then author identity",
        "avatar_url": avatar_url,
        "avatar_sha256": sha256(&normalized),
    }))
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    let directory = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(directory)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let temporary = directory.join(format!(".e-balls-count-{}-{unique}.json", std::process::id()));
    let result = (|| -> Result<()> {
        let bytes = format!("{}\n", serde_json::to_string_pretty(value)?);
        fs::write(&temporary, bytes)?;
        fs::rename(&temporary, path)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn run(args: Args) -> Result<()> {
    let letter = args.letter.as_bytes();
    if letter.len() != 1 || !letter[0].is_ascii_alphabetic() {
        bail!("letter must be one ASCII letter");
    }
    let end = args.end.unwrap_or_else(|| Utc::now().date_naive());
    let start = if let Some(start) = args.start {
        start
    } else {
        if let Some(since) = &args.since {
            if since != "7d" {
                bail!("since currently supports exactly 7d");
            }
        }
        let days = args.days.unwrap_or(7);
        if !(1..=MAX_DAYS).contains(&days) {
            bail!("days must be between 1 and {MAX_DAYS}");
        }
        end - DateDuration::days(days)
    };
    let (mut value, authors) = count(
        &args.repo, &args.r#ref, &args.repository, &args.project,
        start, end, letter[0].to_ascii_lowercase()
    )?;
    if let Some(destination) = &args.avatar_out {
        let contributor = fetch_top_avatar(&args.repository, &authors, destination)?;
        value["source"]["top_contributor"] = contributor;
    }
    let count = value["source"]["total_count"].as_u64().context("missing count")?;
    let commits = value["source"]["total_commits"].as_u64().context("missing commits")?;
    write_json(&args.out, &value)?;
    println!("{commits} commits, {count} letters, {} → {}", value["source"]["commit"], args.out.display());
    Ok(())
}

fn main() -> Result<()> {
    run(Args::parse())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha_validation_and_ascii_count() {
        assert!(is_sha(&"a".repeat(40)));
        assert!(!is_sha("HEAD"));
        assert!(!is_sha(&"g".repeat(40)));
        assert_eq!(count_ascii("éEEE ee".as_bytes(), b'e'), 5);
        assert_eq!(sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }

    #[test]
    fn parse_git_author_and_committer() -> Result<()> {
        let raw = b"tree deadbeef\nauthor Jane Doe <Jane@Example.COM> 1791072000 +0000\ncommitter Joe <joe@example.com> 1791072060 +0000";
        let (key, name, bot) = parse_author(raw)?;
        assert_eq!(key, "email:jane@example.com");
        assert_eq!(name, "Jane Doe");
        assert!(!bot);
        assert_eq!(committer_time(raw)?, 1791072060);
        Ok(())
    }

    #[test]
    fn rank_by_letters_then_commits_then_identity_and_ignore_bots() {
        let one = Author { key: "email:abc@example.com".into(), name: "A".into(), count: 30, commits: 2, shas: vec![], bot: false };
        let two = Author { key: "email:xyz@example.com".into(), name: "B".into(), count: 30, commits: 3, shas: vec![], bot: false };
        let bot = Author { key: "email:bot".into(), name: "B".into(), count: 300, commits: 4, shas: vec![], bot: true };
        let ranked = ranked_authors([one, two, bot].into_iter().map(|a| (a.key.clone(), a)).collect());
        assert_eq!(ranked.len(), 2);
        assert_eq!(ranked[0].key, "email:xyz@example.com");
        assert_eq!(ranked[1].key, "email:abc@example.com");
    }

    #[test]
    fn refuse_bad_repositories() {
        assert!(validate_repository("owner/repo").is_ok());
        for bad in ["owner", "owner/repo/extra", "../repo", "owner/repo name", ""] {
            assert!(validate_repository(bad).is_err(), "{bad}");
        }
    }
}
