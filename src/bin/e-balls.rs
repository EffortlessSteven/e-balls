use anyhow::{bail, Context, Result};
use clap::Parser;
use image::{ImageReader, Rgb, RgbImage};
use release_balls::render::{render_with, Options, Presentation};
use serde::Deserialize;
use serde_json::json;
use std::fs;
use std::io::{Cursor, Read};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Parser)]
#[command(version, about = "Race arbitrary counts with the same head on every ball")]
struct Args {
    /// JSON rows from scripts/count_letters.py, or your own schema-v1 data.
    #[arg(long)]
    data: PathBuf,
    /// Local PNG/JPEG portrait. Required; never fetches avatars or substitutes initials.
    #[arg(long)]
    avatar: PathBuf,
    /// New output directory. Existing directories are never overwritten.
    #[arg(long, default_value = "out")]
    out: PathBuf,
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
            total = total.checked_add(row.count).context("sum of counts exceeds u64")?;
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
    let image = reader.decode().context("avatar must be a valid PNG or JPEG")?.to_rgba8();
    if image.width() == 0 || image.height() == 0 {
        bail!("avatar must not be empty");
    }
    // Keep transparent portraits on the same white canvas as the original renderer.
    Ok(RgbImage::from_fn(image.width(), image.height(), |x, y| {
        let pixel = image.get_pixel(x, y);
        let alpha = u32::from(pixel[3]);
        Rgb(std::array::from_fn(|channel| {
            ((u32::from(pixel[channel]) * alpha + 255 * (255 - alpha) + 127) / 255) as u8
        }))
    }))
}

struct Staging(PathBuf);
impl Drop for Staging {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
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
    };
    // Preserve chronological/input order. Do not rank or normalize away small counts.
    let rows: Vec<_> = data.rows.iter().map(|row| (row.label.clone(), row.count)).collect();
    let parent = args.out.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let staging = Staging(parent.join(format!(".e-balls-{}-{stamp}", std::process::id())));
    fs::create_dir(&staging.0)?;
    let stem = staging.0.join("e-balls");
    let mut files = Vec::new();
    for format in ["mp4", "gif"] {
        if args.format != "both" && args.format != format {
            continue;
        }
        let options = Options {
            width: if format == "gif" { 480 } else { args.width },
            fps: if format == "gif" { 15 } else { args.fps },
            duration: args.duration,
            preset: args.preset.clone(),
            threads: args.threads,
            strategy: if format == "gif" { "dirty" } else { "yuv" }.into(),
        };
        render_with(&rows, &presentation, &stem, &[format], &options)?;
        files.push(json!({"path": format!("e-balls.{format}"), "width": options.width, "fps": options.fps}));
    }
    // Freeze the exact input, including any source receipts not interpreted by this CLI.
    fs::write(staging.0.join("data.json"), &bytes)?;
    image.save(staging.0.join("avatar.png"))?;
    let manifest = json!({
        "schema_version": 1, "renderer": "e-balls", "source_data": "data.json",
        "avatar": "avatar.png", "avatar_policy": "same supplied image on every row",
        "row_order": "input", "speed": "linear count / maximum; fastest crosses in 1 second",
        "duration_seconds": args.duration, "rows": rows, "files": files,
    });
    fs::write(staging.0.join("manifest.json"), format!("{}\n", serde_json::to_string_pretty(&manifest)?))?;
    fs::rename(&staging.0, &args.out).context("could not publish completed output directory")?;
    println!("{}", serde_json::to_string_pretty(&manifest)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn value() -> serde_json::Value {
        json!({"schema_version":1,"title":"e","footer":"source","unit":"e's",
            "rows":[{"label":"Monday","count":0},{"label":"Tuesday","count":4}]})
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
        for (key, bad) in [("schema_version", json!(2)), ("title", json!("")), ("unit", json!("e\n")), ("rows", json!([]))] {
            let mut v = value();
            v[key] = bad;
            assert!(serde_json::from_value::<Data>(v)?.validate().is_err());
        }
        let mut v = value();
        v["rows"][0]["count"] = json!(u64::MAX);
        assert!(serde_json::from_value::<Data>(v)?.validate().is_err());
        Ok(())
    }
}
