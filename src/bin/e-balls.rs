use anyhow::{bail, Context, Result};
use clap::Parser;
use image::{ImageReader, Rgb, RgbImage};
use release_balls::render::{render_with, Options, Presentation, Theme};
use serde::Deserialize;
use serde_json::json;
use std::fs;
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Parser)]
#[command(
    version,
    about = "Race arbitrary counts with the same head on every ball"
)]
struct Args {
    /// JSON rows from e-balls-collect, or your own schema-v1 data.
    #[arg(long)]
    data: PathBuf,
    /// Local PNG/JPEG portrait. Required; never fetches avatars or substitutes initials.
    #[arg(long)]
    avatar: PathBuf,
    /// New output directory. Existing directories are never overwritten.
    #[arg(long, default_value = "out")]
    out: PathBuf,
    /// Optional public directory URL for the generated media links.
    #[arg(long, default_value = "")]
    asset_base_url: String,
    #[arg(long, default_value = "both", value_parser = ["mp4", "gif", "both"])]
    format: String,
    #[arg(long, default_value_t = 1080)]
    width: u32,
    #[arg(long, default_value_t = 60)]
    fps: u32,
    #[arg(long, default_value_t = 16.0)]
    duration: f64,
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=16))]
    threads: u32,
    #[arg(long, default_value = "ultrafast", value_parser = ["ultrafast", "superfast", "veryfast"])]
    preset: String,
}

#[derive(Deserialize)]
struct Data {
    schema_version: u32,
    title: String,
    #[serde(default)]
    subtitle: String,
    footer: String,
    unit: String,
    #[serde(default)]
    unit_singular: Option<String>,
    rows: Vec<Row>,
}

#[derive(Deserialize)]
struct Row {
    label: String,
    count: u64,
}

fn label(value: &str, name: &str, max: usize, empty_ok: bool) -> Result<()> {
    if (!empty_ok && value.trim().is_empty())
        || value.chars().count() > max
        || value.chars().any(char::is_control)
    {
        bail!("{name} must be a single-line label of at most {max} characters");
    }
    Ok(())
}

impl Data {
    fn validate(&self) -> Result<()> {
        if self.schema_version != 1 {
            bail!("unsupported schema_version; expected 1");
        }
        if !(1..=366).contains(&self.rows.len()) {
            bail!("provide 1–366 rows; zero counts are allowed");
        }
        label(&self.title, "title", 240, false)?;
        label(&self.subtitle, "subtitle", 160, true)?;
        label(&self.footer, "footer", 160, false)?;
        label(&self.unit, "unit", 24, false)?;
        if let Some(unit) = &self.unit_singular {
            label(unit, "unit_singular", 24, false)?;
        }
        let mut total = 0_u64;
        for row in &self.rows {
            label(&row.label, "row label", 80, false)?;
            total = total
                .checked_add(row.count)
                .context("sum of counts exceeds u64")?;
        }
        Ok(())
    }
}

fn read_bounded(path: &Path, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    fs::File::open(path)
        .with_context(|| format!("cannot open {}", path.display()))?
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        bail!("{} exceeds the {limit}-byte input limit", path.display());
    }
    Ok(bytes)
}

fn portrait(bytes: &[u8]) -> Result<RgbImage> {
    let mut reader = ImageReader::new(Cursor::new(bytes)).with_guessed_format()?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(4096);
    limits.max_image_height = Some(4096);
    limits.max_alloc = Some(64 * 1024 * 1024);
    reader.limits(limits);
    let image = reader
        .decode()
        .context("avatar must be a valid PNG or JPEG")?
        .to_rgba8();
    if image.width() == 0 || image.height() == 0 {
        bail!("avatar must not be empty");
    }
    // Composite transparency before resizing, using the same cream as the arena.
    let background = Theme::EBalls.background();
    Ok(RgbImage::from_fn(image.width(), image.height(), |x, y| {
        let pixel = image.get_pixel(x, y);
        let alpha = u32::from(pixel[3]);
        Rgb(std::array::from_fn(|channel| {
            ((u32::from(pixel[channel]) * alpha
                + u32::from(background[channel]) * (255 - alpha)
                + 127)
                / 255) as u8
        }))
    }))
}

struct Staging {
    path: PathBuf,
    active: bool,
}

impl Staging {
    fn create(path: PathBuf) -> Result<Self> {
        // Acquire ownership before constructing a cleanup guard. A name collision
        // must never cause Drop to delete a directory belonging to another run.
        fs::create_dir(&path)?;
        Ok(Self { path, active: true })
    }

    fn publish(mut self, destination: &Path) -> Result<()> {
        if fs::symlink_metadata(destination).is_ok() {
            bail!("output already exists; choose a new --out directory");
        }
        fs::rename(&self.path, destination)
            .context("could not publish completed output directory")?;
        self.active = false;
        Ok(())
    }
}

impl Drop for Staging {
    fn drop(&mut self) {
        if self.active {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}

// Join every encoder before returning, including on error, so the staging
// directory cannot be removed while another encoder still owns an output file.
fn render_formats(
    format: &str,
    parallel: bool,
    render: impl Fn(&str) -> Result<serde_json::Value> + Sync,
) -> Result<Vec<serde_json::Value>> {
    if format == "both" && parallel {
        std::thread::scope(|scope| {
            let gif = scope.spawn(|| render("gif"));
            let mp4 = render("mp4");
            let gif = gif
                .join()
                .map_err(|_| anyhow::anyhow!("GIF encoder thread panicked"))?;
            Ok(vec![mp4?, gif?])
        })
    } else {
        ["mp4", "gif"]
            .into_iter()
            .filter(|candidate| format == "both" || format == *candidate)
            .map(render)
            .collect()
    }
}

fn media_link(base: &str, filename: &str) -> Result<String> {
    if base.is_empty() {
        return Ok(filename.to_owned());
    }
    if base.chars().any(char::is_control) {
        bail!("asset-base-url must not contain control characters");
    }
    let mut url = url::Url::parse(base).context("invalid asset-base-url")?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        bail!(
            "asset-base-url must be an HTTP(S) directory URL without credentials, query or fragment"
        );
    }
    url.path_segments_mut()
        .map_err(|_| anyhow::anyhow!("asset-base-url must support path segments"))?
        .pop_if_empty()
        .push(filename);
    Ok(url.as_str().replace('(', "%28").replace(')', "%29"))
}

fn media_markdown(base: &str, format: &str) -> Result<String> {
    let mut markdown = String::new();
    if format != "mp4" {
        markdown.push_str(&format!("![e-balls]({})\n", media_link(base, "e-balls.gif")?));
    }
    if format != "gif" {
        markdown.push_str(&format!("\n[MP4]({})\n", media_link(base, "e-balls.mp4")?));
    }
    Ok(markdown)
}

fn github_output_records(directory: &Path) -> Result<String> {
    let directory = if directory.is_absolute() {
        directory.to_owned()
    } else {
        std::env::current_dir()?.join(directory)
    };
    let mut records = String::new();
    for (key, path) in [
        ("directory", directory.clone()),
        ("markdown", directory.join("embed.md")),
        ("manifest", directory.join("manifest.json")),
        ("data", directory.join("data.json")),
    ] {
        let path = path.to_str().context("GitHub output path must be UTF-8")?;
        if path.contains(['\n', '\r']) {
            bail!("GitHub output path must not contain newlines");
        }
        records.push_str(&format!("{key}={path}\n"));
    }
    Ok(records)
}

fn main() -> Result<()> {
    let args = Args::parse();
    if !(320..=2160).contains(&args.width)
        || !args.width.is_multiple_of(2)
        || !(1..=60).contains(&args.fps)
        || !args.duration.is_finite()
        || !(0.1..=60.0).contains(&args.duration)
    {
        bail!("use even width 320–2160, fps 1–60, duration 0.1–60");
    }
    if fs::symlink_metadata(&args.out).is_ok() {
        bail!("output already exists; choose a new --out directory");
    }
    // Validate metadata and output-channel permissions before encoding anything.
    let markdown = media_markdown(&args.asset_base_url, &args.format)?;
    let github_output = if let Some(path) = std::env::var_os("GITHUB_OUTPUT") {
        let records = github_output_records(&args.out)?;
        let file = fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(path)
            .context("cannot open GITHUB_OUTPUT")?;
        Some((file, records))
    } else {
        None
    };
    let bytes = read_bounded(&args.data, 32 * 1024 * 1024)?;
    let data: Data = serde_json::from_slice(&bytes).context("invalid rows JSON")?;
    data.validate()?;
    let image = portrait(&read_bounded(&args.avatar, 8 * 1024 * 1024)?)?;
    let presentation = Presentation {
        title: &data.title,
        subtitle: &data.subtitle,
        footer: &data.footer,
        singular: data.unit_singular.as_deref().unwrap_or(&data.unit),
        plural: &data.unit,
        avatar: Some(&image),
        theme: Theme::EBalls,
    };
    // Preserve chronological/input order. Do not rank or normalize away small counts.
    let rows: Vec<_> = data
        .rows
        .iter()
        .map(|row| (row.label.clone(), row.count))
        .collect();
    let parent = args
        .out
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let staging = Staging::create(parent.join(format!(".e-balls-{}-{stamp}", std::process::id())))?;
    let stem = staging.path.join("e-balls");
    let parallel = args.threads > 1
        && std::thread::available_parallelism().is_ok_and(|cores| cores.get() > 1);
    let files = render_formats(&args.format, parallel, |format| {
        let options = Options {
            width: if format == "gif" { 480 } else { args.width },
            fps: if format == "gif" { 15 } else { args.fps },
            duration: args.duration,
            preset: args.preset.clone(),
            threads: args.threads,
            strategy: if format == "gif" { "dirty" } else { "yuv" }.into(),
        };
        render_with(&rows, &presentation, &stem, &[format], &options)?;
        Ok(json!({
            "path": format!("e-balls.{format}"),
            "width": options.width,
            "fps": options.fps,
        }))
    })?;
    // Freeze the exact input, including any source receipts not interpreted by this CLI.
    fs::write(staging.path.join("data.json"), &bytes)?;
    image.save(staging.path.join("avatar.png"))?;
    fs::write(staging.path.join("embed.md"), markdown)?;
    let manifest = json!({
        "schema_version": 1, "renderer": "e-balls", "markdown": "embed.md",
        "theme": {"name": "teal-cream", "background": "#f5f1e8", "foreground": "#156b76",
            "primary_font": "IBM Plex Sans Regular", "data_font": "IBM Plex Mono Regular",
            "font_sources": serde_json::from_str::<serde_json::Value>(include_str!("../../assets/plex-manifest.json"))?}, "source_data": "data.json",
        "avatar": "avatar.png", "avatar_policy": "same supplied image on every row",
        "row_order": "input", "speed": "linear count / maximum; fastest crosses in 1 second",
        "duration_seconds": args.duration, "rows": rows, "files": files,
    });
    fs::write(
        staging.path.join("manifest.json"),
        format!("{}\n", serde_json::to_string_pretty(&manifest)?),
    )?;
    staging.publish(&args.out)?;
    if let Some((mut file, records)) = github_output {
        file.write_all(records.as_bytes())
            .context("could not write GitHub Action outputs")?;
    }
    println!("{}", serde_json::to_string_pretty(&manifest)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn markdown_matches_selected_formats_and_encodes_urls() -> Result<()> {
        assert_eq!(media_markdown("", "gif")?, "![e-balls](e-balls.gif)\n");
        assert_eq!(media_markdown("", "mp4")?, "\n[MP4](e-balls.mp4)\n");
        let both = media_markdown("https://example.test/clip(1)/", "both")?;
        assert!(both.contains("https://example.test/clip%281%29/e-balls.gif"));
        assert!(both.contains("https://example.test/clip%281%29/e-balls.mp4"));
        Ok(())
    }

    #[test]
    fn reject_ambiguous_or_unsafe_asset_prefixes() {
        for prefix in [
            "javascript:alert(1)",
            "file:///tmp",
            "https://user:password@example.test",
            "https://example.test/?query=value",
            "https://example.test/#fragment",
            "https://example.test/\nforge",
        ] {
            assert!(media_markdown(prefix, "both").is_err(), "{prefix}");
        }
    }

    #[test]
    fn output_records_are_absolute_and_single_line() -> Result<()> {
        let records = github_output_records(Path::new("out"))?;
        assert_eq!(records.lines().count(), 4);
        let expected = std::env::current_dir()?.join("out").join("embed.md");
        assert!(records.contains(&format!("markdown={}\n", expected.display())));
        assert!(github_output_records(Path::new("out\nforged=value")).is_err());
        assert!(github_output_records(Path::new("out\rforged=value")).is_err());
        Ok(())
    }

    #[test]
    fn parallel_formats_overlap_but_keep_manifest_order() -> Result<()> {
        let barrier = std::sync::Barrier::new(2);
        let formats = render_formats("both", true, |format| {
            barrier.wait();
            Ok(json!(format))
        })?;
        assert_eq!(formats, vec![json!("mp4"), json!("gif")]);
        Ok(())
    }

    #[test]
    fn format_error_waits_for_other_encoder() {
        use std::sync::atomic::{AtomicBool, Ordering};
        let finished = AtomicBool::new(false);
        let result = render_formats("both", true, |format| {
            if format == "mp4" {
                bail!("synthetic encoder failure");
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
            finished.store(true, Ordering::SeqCst);
            Ok(json!(format))
        });
        assert!(result.is_err());
        assert!(finished.load(Ordering::SeqCst));
    }

    #[test]
    fn worker_panic_becomes_a_render_error() {
        let result = render_formats("both", true, |format| {
            if format == "gif" {
                panic!("synthetic worker failure");
            }
            Ok(json!(format))
        });
        assert!(result.unwrap_err().to_string().contains("panicked"));
    }

    #[test]
    fn serial_and_single_formats_preserve_selection() -> Result<()> {
        for parallel in [false, true] {
            assert_eq!(
                render_formats("mp4", parallel, |format| Ok(json!(format)))?,
                vec![json!("mp4")]
            );
            assert_eq!(
                render_formats("gif", parallel, |format| Ok(json!(format)))?,
                vec![json!("gif")]
            );
        }
        assert_eq!(
            render_formats("both", false, |format| Ok(json!(format)))?,
            vec![json!("mp4"), json!("gif")]
        );
        Ok(())
    }

    fn value() -> serde_json::Value {
        json!({"schema_version":1,"title":"e","footer":"source","unit":"e's",
            "rows":[{"label":"Monday","count":0},{"label":"Tuesday","count":4}]})
    }

    #[test]
    fn transparent_portrait_flattens_to_cream() -> Result<()> {
        let mut rgba = image::RgbaImage::new(3, 1);
        rgba.put_pixel(0, 0, image::Rgba([255, 0, 255, 0]));
        rgba.put_pixel(1, 0, image::Rgba([21, 107, 118, 128]));
        rgba.put_pixel(2, 0, image::Rgba([21, 107, 118, 255]));
        let mut bytes = Cursor::new(Vec::new());
        rgba.write_to(&mut bytes, image::ImageFormat::Png)?;
        let image = portrait(bytes.get_ref())?;
        assert_eq!(image.get_pixel(0, 0).0, [245, 241, 232]);
        assert_eq!(image.get_pixel(1, 0).0, [133, 174, 175]);
        assert_eq!(image.get_pixel(2, 0).0, [21, 107, 118]);
        Ok(())
    }

    #[test]
    fn accepts_arbitrary_rows_and_zeroes() -> Result<()> {
        let data: Data = serde_json::from_value(value())?;
        data.validate()?;
        assert_eq!(data.rows[0].label, "Monday");
        assert_eq!(data.rows[1].count, 4);
        Ok(())
    }

    #[test]
    fn rejects_bad_counts_schema_and_labels() -> Result<()> {
        for count in [json!(-1), json!(1.5), json!("4")] {
            let mut v = value();
            v["rows"][0]["count"] = count;
            assert!(serde_json::from_value::<Data>(v).is_err());
        }
        for (key, bad) in [
            ("schema_version", json!(2)),
            ("title", json!("")),
            ("unit", json!("e\n")),
            ("rows", json!([])),
        ] {
            let mut v = value();
            v[key] = bad;
            assert!(serde_json::from_value::<Data>(v)?.validate().is_err());
        }
        let mut v = value();
        v["rows"][0]["count"] = json!(u64::MAX);
        assert!(serde_json::from_value::<Data>(v)?.validate().is_err());
        Ok(())
    }

    #[test]
    fn staging_collision_does_not_delete_another_runs_output() -> Result<()> {
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
        let path = std::env::temp_dir().join(format!(
            "e-balls-staging-test-{}-{stamp}",
            std::process::id()
        ));
        let owner = Staging::create(path.clone())?;
        fs::write(path.join("keep.txt"), b"keep")?;
        assert!(Staging::create(path.clone()).is_err());
        assert_eq!(fs::read(path.join("keep.txt"))?, b"keep");
        drop(owner);
        assert!(!path.exists());
        Ok(())
    }
}
