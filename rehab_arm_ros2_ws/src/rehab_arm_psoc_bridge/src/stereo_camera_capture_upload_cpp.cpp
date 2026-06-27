#include <opencv2/dnn.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

namespace {

constexpr const char *kSchemaVersion = "stereo_rgb_yolo_context_v1";
constexpr const char *kControlBoundary = "stereo_vision_context_only_not_motion_permission";

struct Options {
  std::string robot_id = "rehab-arm-alpha";
  std::string device_id = "nanopi-m5";
  std::string project_id;
  std::string left_device = "/dev/video45";
  std::string right_device = "/dev/video47";
  std::string left_camera_id = "left_rgb";
  std::string right_camera_id = "right_rgb";
  std::string output_dir = "~/rehab_arm_stereo_frames";
  int width = 640;
  int height = 480;
  bool rotate_180 = false;
  int sequence = 1;
  double baseline_m = std::numeric_limits<double>::quiet_NaN();
  std::string stereo_calibration_id;
  std::string api_base;
  std::string relay_token;
  bool upload = false;
  bool pretty = false;
  bool analyze_image_quality = false;
  std::string ssd_model;
  std::string ssd_prototxt;
  std::string ssd_labels;
  double ssd_confidence_threshold = 0.35;
  bool detect_right_ssd = false;
  std::string yolox_model;
  std::string yolox_labels;
  int yolox_input_size = 416;
  double yolox_confidence_threshold = 0.25;
  double yolox_nms_threshold = 0.45;
  bool detect_right_yolox = false;
  bool auto_target_from_detections = false;
  std::vector<std::string> target_label_allowlist;
  bool stereo_associate_target = false;
  double max_stereo_vertical_delta_px = 80.0;
  int loop_count = 1;
  int interval_ms = 0;
};

struct Detection {
  std::string label;
  double confidence = 0.0;
  cv::Rect bbox;
  std::string image_ref;
  std::string image_side;
  std::string source = "opencv_dnn_mobilenet_ssd";
};

struct Quality {
  double left_mean_luma = 0.0;
  double right_mean_luma = 0.0;
  double left_sharpness = 0.0;
  double right_sharpness = 0.0;
  double pair_difference = 0.0;
  bool usable = true;
  std::string warning;
};

struct LoopTelemetry {
  int loop_index = 0;
  int loop_count = 1;
  int interval_ms = 0;
  int sequence = 1;
  double frame_process_ms = 0.0;
  double loop_elapsed_ms = 0.0;
};

std::string usage() {
  return R"(Capture two USB camera frames, run OpenCV DNN MobileNet-SSD, and optionally upload a perception-only stereo VLA-V context.

Required:
  --project-id <id>

Common:
  --api-base http://106.55.62.122:8011 --upload
  --left-device /dev/video45 --right-device /dev/video47 --rotate-180
  --baseline-m 0.06 --sequence 1 --pretty
  --ssd-model /home/pi/rehab_arm_models/ssd/mobilenet_iter_73000.caffemodel
  --ssd-prototxt /home/pi/rehab_arm_models/ssd/deploy.prototxt
  --ssd-labels /home/pi/rehab_arm_models/ssd/voc21.txt
  --detect-right-ssd --auto-target-from-detections --target-label-allowlist bottle,cup
  --yolox-onnx /home/pi/rehab_arm_models/yolo/yolox_nano.onnx
  --yolox-labels /home/pi/rehab_arm_models/yolo/coco80.txt --detect-right-yolox
  --stereo-associate-target --analyze-image-quality
  --loop-count 10 --interval-ms 200

Safety:
  This executable only uploads stereo_vision_context. It publishes no ROS motion topics and sends no CAN frames.
)";
}

std::string json_escape(const std::string &value) {
  std::ostringstream out;
  for (const char c : value) {
    switch (c) {
    case '"': out << "\\\""; break;
    case '\\': out << "\\\\"; break;
    case '\b': out << "\\b"; break;
    case '\f': out << "\\f"; break;
    case '\n': out << "\\n"; break;
    case '\r': out << "\\r"; break;
    case '\t': out << "\\t"; break;
    default:
      if (static_cast<unsigned char>(c) < 0x20) {
        out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
      } else {
        out << c;
      }
    }
  }
  return out.str();
}

std::string quote(const std::string &value) {
  return "\"" + json_escape(value) + "\"";
}

std::vector<std::string> split_csv(const std::string &text) {
  std::vector<std::string> items;
  std::stringstream ss(text);
  std::string item;
  while (std::getline(ss, item, ',')) {
    item.erase(item.begin(), std::find_if(item.begin(), item.end(), [](unsigned char ch) { return !std::isspace(ch); }));
    item.erase(std::find_if(item.rbegin(), item.rend(), [](unsigned char ch) { return !std::isspace(ch); }).base(), item.end());
    if (!item.empty()) {
      items.push_back(item);
    }
  }
  return items;
}

bool contains(const std::vector<std::string> &items, const std::string &value) {
  return std::find(items.begin(), items.end(), value) != items.end();
}

std::string expand_user_path(const std::string &path) {
  if (path.rfind("~/", 0) != 0) {
    return path;
  }
  const char *home = std::getenv("HOME");
  if (home == nullptr || std::string(home).empty()) {
    return path;
  }
  return std::string(home) + path.substr(1);
}

std::string sanitize_identifier(std::string value) {
  for (char &ch : value) {
    const bool ok = std::isalnum(static_cast<unsigned char>(ch)) || ch == '-' || ch == '_';
    if (!ok) {
      ch = '_';
    }
  }
  return value;
}

std::string utc_timestamp() {
  const auto now = std::chrono::system_clock::now();
  const std::time_t t = std::chrono::system_clock::to_time_t(now);
  std::tm tm{};
#ifdef _WIN32
  gmtime_s(&tm, &t);
#else
  gmtime_r(&t, &tm);
#endif
  std::ostringstream out;
  out << std::put_time(&tm, "%Y%m%dT%H%M%SZ");
  return out.str();
}

double unix_time_seconds() {
  const auto now = std::chrono::system_clock::now().time_since_epoch();
  return std::chrono::duration<double>(now).count();
}

Options parse_args(int argc, char **argv) {
  Options options;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto require_value = [&](const std::string &name) -> std::string {
      if (i + 1 >= argc) {
        throw std::runtime_error(name + " requires a value");
      }
      return argv[++i];
    };
    if (arg == "--help" || arg == "-h") {
      std::cout << usage();
      std::exit(0);
    } else if (arg == "--robot-id") {
      options.robot_id = require_value(arg);
    } else if (arg == "--device-id") {
      options.device_id = require_value(arg);
    } else if (arg == "--project-id") {
      options.project_id = require_value(arg);
    } else if (arg == "--left-device") {
      options.left_device = require_value(arg);
    } else if (arg == "--right-device") {
      options.right_device = require_value(arg);
    } else if (arg == "--left-camera-id") {
      options.left_camera_id = require_value(arg);
    } else if (arg == "--right-camera-id") {
      options.right_camera_id = require_value(arg);
    } else if (arg == "--output-dir") {
      options.output_dir = require_value(arg);
    } else if (arg == "--width") {
      options.width = std::stoi(require_value(arg));
    } else if (arg == "--height") {
      options.height = std::stoi(require_value(arg));
    } else if (arg == "--rotate-180") {
      options.rotate_180 = true;
    } else if (arg == "--sequence") {
      options.sequence = std::stoi(require_value(arg));
    } else if (arg == "--baseline-m") {
      options.baseline_m = std::stod(require_value(arg));
    } else if (arg == "--stereo-calibration-id") {
      options.stereo_calibration_id = require_value(arg);
    } else if (arg == "--api-base") {
      options.api_base = require_value(arg);
    } else if (arg == "--relay-token") {
      options.relay_token = require_value(arg);
    } else if (arg == "--upload") {
      options.upload = true;
    } else if (arg == "--pretty") {
      options.pretty = true;
    } else if (arg == "--analyze-image-quality") {
      options.analyze_image_quality = true;
    } else if (arg == "--ssd-model") {
      options.ssd_model = require_value(arg);
    } else if (arg == "--ssd-prototxt") {
      options.ssd_prototxt = require_value(arg);
    } else if (arg == "--ssd-labels") {
      options.ssd_labels = require_value(arg);
    } else if (arg == "--ssd-confidence-threshold") {
      options.ssd_confidence_threshold = std::stod(require_value(arg));
    } else if (arg == "--detect-right-ssd") {
      options.detect_right_ssd = true;
    } else if (arg == "--yolox-onnx") {
      options.yolox_model = require_value(arg);
    } else if (arg == "--yolox-labels") {
      options.yolox_labels = require_value(arg);
    } else if (arg == "--yolox-input-size") {
      options.yolox_input_size = std::stoi(require_value(arg));
    } else if (arg == "--yolox-confidence-threshold") {
      options.yolox_confidence_threshold = std::stod(require_value(arg));
    } else if (arg == "--yolox-nms-threshold") {
      options.yolox_nms_threshold = std::stod(require_value(arg));
    } else if (arg == "--detect-right-yolox") {
      options.detect_right_yolox = true;
    } else if (arg == "--auto-target-from-detections") {
      options.auto_target_from_detections = true;
    } else if (arg == "--target-label-allowlist") {
      options.target_label_allowlist = split_csv(require_value(arg));
    } else if (arg == "--stereo-associate-target") {
      options.stereo_associate_target = true;
    } else if (arg == "--max-stereo-vertical-delta-px") {
      options.max_stereo_vertical_delta_px = std::stod(require_value(arg));
    } else if (arg == "--loop-count") {
      options.loop_count = std::stoi(require_value(arg));
    } else if (arg == "--interval-ms") {
      options.interval_ms = std::stoi(require_value(arg));
    } else {
      throw std::runtime_error("unknown argument: " + arg);
    }
  }
  if (options.project_id.empty()) {
    throw std::runtime_error("--project-id is required");
  }
  if (options.upload && options.api_base.empty()) {
    throw std::runtime_error("--api-base is required with --upload");
  }
  const bool has_any_ssd_arg = !options.ssd_model.empty() || !options.ssd_prototxt.empty() || !options.ssd_labels.empty();
  const bool has_all_ssd_args = !options.ssd_model.empty() && !options.ssd_prototxt.empty() && !options.ssd_labels.empty();
  if (has_any_ssd_arg && !has_all_ssd_args) {
    throw std::runtime_error("--ssd-model, --ssd-prototxt, and --ssd-labels must be provided together");
  }
  const bool has_any_yolox_arg = !options.yolox_model.empty() || !options.yolox_labels.empty();
  const bool has_all_yolox_args = !options.yolox_model.empty() && !options.yolox_labels.empty();
  if (has_any_yolox_arg && !has_all_yolox_args) {
    throw std::runtime_error("--yolox-onnx and --yolox-labels must be provided together");
  }
  if (options.yolox_input_size < 32) {
    throw std::runtime_error("--yolox-input-size must be >= 32");
  }
  if (options.loop_count < 1) {
    throw std::runtime_error("--loop-count must be >= 1");
  }
  if (options.interval_ms < 0) {
    throw std::runtime_error("--interval-ms must be >= 0");
  }
  return options;
}

std::vector<std::string> load_labels(const std::string &path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("failed to open labels file: " + path);
  }
  std::vector<std::string> labels;
  std::string line;
  while (std::getline(in, line)) {
    line.erase(line.begin(), std::find_if(line.begin(), line.end(), [](unsigned char ch) { return !std::isspace(ch); }));
    line.erase(std::find_if(line.rbegin(), line.rend(), [](unsigned char ch) { return !std::isspace(ch); }).base(), line.end());
    if (!line.empty()) {
      labels.push_back(line);
    }
  }
  if (labels.empty()) {
    throw std::runtime_error("labels file is empty: " + path);
  }
  return labels;
}

cv::VideoCapture open_capture(const std::string &device, int width, int height) {
  cv::VideoCapture capture(device, cv::CAP_V4L2);
  if (!capture.isOpened()) {
    throw std::runtime_error("OpenCV failed to open capture device: " + device);
  }
  capture.set(cv::CAP_PROP_FRAME_WIDTH, width);
  capture.set(cv::CAP_PROP_FRAME_HEIGHT, height);
  capture.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
  return capture;
}

cv::Mat read_frame(cv::VideoCapture &capture, const std::string &device, bool rotate_180, int flush_count = 2) {
  cv::Mat frame;
  for (int i = 0; i < flush_count; ++i) {
    capture >> frame;
  }
  if (frame.empty()) {
    throw std::runtime_error("capture produced an empty frame: " + device);
  }
  if (rotate_180) {
    cv::rotate(frame, frame, cv::ROTATE_180);
  }
  return frame;
}

std::pair<std::string, std::string> make_frame_paths(const Options &options, int sequence) {
  const fs::path output_dir(expand_user_path(options.output_dir));
  fs::create_directories(output_dir);
  std::ostringstream base;
  base << sanitize_identifier(options.robot_id + "__" + options.device_id)
       << "__stereo__" << utc_timestamp() << "__"
       << std::setw(4) << std::setfill('0') << sequence;
  const fs::path left = output_dir / (base.str() + "__left.jpg");
  const fs::path right = output_dir / (base.str() + "__right.jpg");
  return {left.string(), right.string()};
}

double mean_luma(const cv::Mat &image) {
  cv::Mat gray;
  cv::cvtColor(image, gray, cv::COLOR_BGR2GRAY);
  return cv::mean(gray)[0];
}

double sharpness_proxy(const cv::Mat &image) {
  cv::Mat gray;
  cv::cvtColor(image, gray, cv::COLOR_BGR2GRAY);
  cv::Mat laplacian;
  cv::Laplacian(gray, laplacian, CV_64F);
  cv::Scalar mean;
  cv::Scalar stddev;
  cv::meanStdDev(laplacian, mean, stddev);
  return stddev[0];
}

Quality analyze_quality(const cv::Mat &left, const cv::Mat &right) {
  Quality q;
  q.left_mean_luma = mean_luma(left);
  q.right_mean_luma = mean_luma(right);
  q.left_sharpness = sharpness_proxy(left);
  q.right_sharpness = sharpness_proxy(right);
  cv::Mat left_small;
  cv::Mat right_small;
  cv::resize(left, left_small, cv::Size(64, 64));
  cv::resize(right, right_small, cv::Size(64, 64));
  cv::Mat diff;
  cv::absdiff(left_small, right_small, diff);
  q.pair_difference = cv::mean(diff)[0];
  if (std::min(q.left_mean_luma, q.right_mean_luma) < 8.0) {
    q.usable = false;
    q.warning = "too dark";
  }
  return q;
}

std::vector<Detection> detect_ssd(const cv::Mat &image,
                                  const std::string &image_ref,
                                  const std::string &image_side,
                                  cv::dnn::Net &net,
                                  const std::vector<std::string> &labels,
                                  double confidence_threshold) {
  cv::Mat blob = cv::dnn::blobFromImage(image, 0.007843, cv::Size(300, 300), 127.5);
  net.setInput(blob);
  cv::Mat output = net.forward();
  cv::Mat detections(output.size[2], output.size[3], CV_32F, output.ptr<float>());

  std::vector<Detection> parsed;
  for (int i = 0; i < detections.rows; ++i) {
    const float confidence = detections.at<float>(i, 2);
    if (confidence < confidence_threshold) {
      continue;
    }
    const int class_id = static_cast<int>(detections.at<float>(i, 1));
    const std::string label = class_id >= 0 && class_id < static_cast<int>(labels.size()) ? labels[class_id] : "class_" + std::to_string(class_id);
    int x1 = static_cast<int>(std::round(detections.at<float>(i, 3) * image.cols));
    int y1 = static_cast<int>(std::round(detections.at<float>(i, 4) * image.rows));
    int x2 = static_cast<int>(std::round(detections.at<float>(i, 5) * image.cols));
    int y2 = static_cast<int>(std::round(detections.at<float>(i, 6) * image.rows));
    x1 = std::clamp(x1, 0, image.cols - 1);
    y1 = std::clamp(y1, 0, image.rows - 1);
    x2 = std::clamp(x2, x1 + 1, image.cols);
    y2 = std::clamp(y2, y1 + 1, image.rows);
    parsed.push_back({label, confidence, cv::Rect(x1, y1, x2 - x1, y2 - y1), image_ref, image_side});
  }
  std::sort(parsed.begin(), parsed.end(), [](const Detection &a, const Detection &b) {
    return a.confidence > b.confidence;
  });
  return parsed;
}

std::vector<Detection> detect_yolox(const cv::Mat &image,
                                    const std::string &image_ref,
                                    const std::string &image_side,
                                    cv::dnn::Net &net,
                                    const std::vector<std::string> &labels,
                                    int input_size,
                                    double confidence_threshold,
                                    double nms_threshold) {
  const int original_width = image.cols;
  const int original_height = image.rows;
  const double resize_ratio = std::min(input_size / static_cast<double>(std::max(1, original_width)),
                                       input_size / static_cast<double>(std::max(1, original_height)));
  const int resized_width = std::max(1, static_cast<int>(std::round(original_width * resize_ratio)));
  const int resized_height = std::max(1, static_cast<int>(std::round(original_height * resize_ratio)));

  cv::Mat resized;
  cv::resize(image, resized, cv::Size(resized_width, resized_height));
  cv::Mat canvas(input_size, input_size, image.type(), cv::Scalar(114, 114, 114));
  resized.copyTo(canvas(cv::Rect(0, 0, resized_width, resized_height)));

  cv::Mat blob = cv::dnn::blobFromImage(canvas, 1.0, cv::Size(input_size, input_size), cv::Scalar(), true, false);
  net.setInput(blob);
  cv::Mat output = net.forward();
  cv::Mat rows(output.size[1], output.size[2], CV_32F, output.ptr<float>());

  std::vector<cv::Rect> boxes;
  std::vector<float> confidences;
  std::vector<int> class_ids;
  int row_index = 0;
  for (const int stride : {8, 16, 32}) {
    const int grid_h = input_size / stride;
    const int grid_w = input_size / stride;
    for (int gy = 0; gy < grid_h; ++gy) {
      for (int gx = 0; gx < grid_w; ++gx, ++row_index) {
        const float *row = rows.ptr<float>(row_index);
        const float objectness = row[4];
        int best_class_id = -1;
        float best_class_score = 0.0F;
        for (int class_id = 0; class_id < static_cast<int>(labels.size()); ++class_id) {
          const float class_score = row[5 + class_id];
          if (class_score > best_class_score) {
            best_class_score = class_score;
            best_class_id = class_id;
          }
        }
        const float confidence = objectness * best_class_score;
        if (confidence < confidence_threshold || best_class_id < 0) {
          continue;
        }
        const double cx = (row[0] + gx) * stride;
        const double cy = (row[1] + gy) * stride;
        const double box_w = std::exp(row[2]) * stride;
        const double box_h = std::exp(row[3]) * stride;
        int x = static_cast<int>(std::round((cx - box_w / 2.0) / resize_ratio));
        int y = static_cast<int>(std::round((cy - box_h / 2.0) / resize_ratio));
        int w = static_cast<int>(std::round(box_w / resize_ratio));
        int h = static_cast<int>(std::round(box_h / resize_ratio));
        x = std::clamp(x, 0, std::max(0, original_width - 1));
        y = std::clamp(y, 0, std::max(0, original_height - 1));
        w = std::clamp(w, 1, std::max(1, original_width - x));
        h = std::clamp(h, 1, std::max(1, original_height - y));
        boxes.emplace_back(x, y, w, h);
        confidences.push_back(confidence);
        class_ids.push_back(best_class_id);
      }
    }
  }

  std::vector<int> keep;
  cv::dnn::NMSBoxes(boxes, confidences, static_cast<float>(confidence_threshold), static_cast<float>(nms_threshold), keep);
  std::vector<Detection> parsed;
  for (const int index : keep) {
    const int class_id = class_ids[index];
    const std::string label = class_id >= 0 && class_id < static_cast<int>(labels.size()) ? labels[class_id] : "class_" + std::to_string(class_id);
    parsed.push_back({label, confidences[index], boxes[index], image_ref, image_side, "opencv_dnn_yolox"});
  }
  std::sort(parsed.begin(), parsed.end(), [](const Detection &a, const Detection &b) {
    return a.confidence > b.confidence;
  });
  return parsed;
}

std::optional<Detection> select_target(const std::vector<Detection> &detections, const std::vector<std::string> &allowlist) {
  std::optional<Detection> best;
  for (const auto &detection : detections) {
    if (detection.image_side != "left") {
      continue;
    }
    if (!allowlist.empty() && !contains(allowlist, detection.label)) {
      continue;
    }
    if (!best || detection.confidence > best->confidence) {
      best = detection;
    }
  }
  return best;
}

cv::Point2d center(const cv::Rect &rect) {
  return {rect.x + rect.width / 2.0, rect.y + rect.height / 2.0};
}

std::optional<Detection> associate_right_detection(const Detection &target,
                                                   const std::vector<Detection> &detections,
                                                   double max_vertical_delta) {
  const cv::Point2d left_center = center(target.bbox);
  std::optional<Detection> best;
  double best_score = -1e9;
  for (const auto &detection : detections) {
    if (detection.image_side != "right" || detection.label != target.label) {
      continue;
    }
    const cv::Point2d right_center = center(detection.bbox);
    const double vertical_delta = std::abs(left_center.y - right_center.y);
    if (vertical_delta > max_vertical_delta) {
      continue;
    }
    const double horizontal_delta = std::abs(left_center.x - right_center.x);
    const double score = detection.confidence - vertical_delta * 0.001 - horizontal_delta * 0.0001;
    if (score > best_score) {
      best_score = score;
      best = detection;
    }
  }
  return best;
}

std::string bbox_json(const cv::Rect &bbox) {
  std::ostringstream out;
  out << "[" << bbox.x << "," << bbox.y << "," << bbox.width << "," << bbox.height << "]";
  return out.str();
}

std::string detections_json(const std::vector<Detection> &detections) {
  std::ostringstream out;
  out << "[";
  for (size_t i = 0; i < detections.size(); ++i) {
    const auto &d = detections[i];
    if (i) {
      out << ",";
    }
    out << "{"
        << "\"label\":" << quote(d.label) << ","
        << "\"confidence\":" << std::fixed << std::setprecision(3) << d.confidence << ","
        << "\"bbox_xywh\":" << bbox_json(d.bbox) << ","
        << "\"image_ref\":" << quote(d.image_ref) << ","
        << "\"image_side\":" << quote(d.image_side) << ","
        << "\"source\":" << quote(d.source)
        << "}";
  }
  out << "]";
  return out.str();
}

std::string target_json(const std::optional<Detection> &target,
                        const std::optional<Detection> &right_match,
                        bool stereo_association_requested) {
  if (!target) {
    return "{}";
  }
  std::ostringstream out;
  out << "{"
      << "\"label\":" << quote(target->label) << ","
      << "\"confidence\":" << std::fixed << std::setprecision(3) << target->confidence << ","
      << "\"source\":" << quote(target->source) << ","
      << "\"bbox_xywh\":" << bbox_json(target->bbox) << ","
      << "\"image_ref\":" << quote(target->image_ref) << ","
      << "\"image_side\":" << quote(target->image_side);
  if (right_match) {
    const cv::Point2d left_center = center(target->bbox);
    const cv::Point2d right_center = center(right_match->bbox);
    out << ",\"stereo_observation\":{"
        << "\"label\":" << quote(target->label) << ","
        << "\"left_bbox_xywh\":" << bbox_json(target->bbox) << ","
        << "\"right_bbox_xywh\":" << bbox_json(right_match->bbox) << ","
        << "\"left_center_px\":[" << std::fixed << std::setprecision(2) << left_center.x << "," << left_center.y << "],"
        << "\"right_center_px\":[" << right_center.x << "," << right_center.y << "],"
        << "\"horizontal_disparity_px\":" << left_center.x - right_center.x << ","
        << "\"vertical_center_delta_px\":" << std::abs(left_center.y - right_center.y) << ","
        << "\"right_confidence\":" << std::setprecision(3) << right_match->confidence << ","
        << "\"depth_status\":\"uncalibrated_pixel_disparity_only\""
        << "}";
  } else if (stereo_association_requested) {
    out << ",\"stereo_observation_status\":\"no_right_semantic_match\"";
  }
  out << "}";
  return out.str();
}

std::string pixel_servo_hint_json(const Options &options,
                                  const cv::Mat &left,
                                  const std::optional<Detection> &target,
                                  const std::optional<Detection> &right_match) {
  std::ostringstream out;
  out << "{"
      << "\"schema_version\":\"uncalibrated_pixel_servo_hint_v1\","
      << "\"calibration_state\":\"uncalibrated\","
      << "\"coordinate_frame\":\"left_image_px\","
      << "\"control_boundary\":\"pixel_servo_hint_only_not_motion_permission\",";
  if (!target) {
    out << "\"state\":\"waiting_target\","
        << "\"next_step\":\"hold_observe\","
        << "\"reason\":\"no_target_detection\","
        << "\"requires_fresh_frame\":true,"
        << "\"metric_depth_available\":false"
        << "}";
    return out.str();
  }

  const cv::Point2d left_center = center(target->bbox);
  const double frame_width = std::max(1, left.cols > 0 ? left.cols : options.width);
  const double frame_height = std::max(1, left.rows > 0 ? left.rows : options.height);
  const double offset_x = (left_center.x - frame_width / 2.0) / (frame_width / 2.0);
  const double offset_y = (left_center.y - frame_height / 2.0) / (frame_height / 2.0);
  const double deadband = 0.16;
  const bool centered_x = std::abs(offset_x) <= deadband;
  const bool centered_y = std::abs(offset_y) <= deadband;
  const bool has_right_match = right_match.has_value();

  std::string state = "observe_more";
  std::string next_step = "hold_observe";
  std::string reason = "single_frame_pixel_hint";
  if (!has_right_match) {
    state = "waiting_stereo_match";
    reason = "no_right_semantic_match";
  } else if (centered_x && centered_y) {
    state = "centered_single_frame";
    next_step = "hold_centered_then_reobserve";
  } else if (!centered_x) {
    state = "servo_adjust";
    next_step = offset_x < 0.0 ? "dry_run_shift_left" : "dry_run_shift_right";
  } else if (!centered_y) {
    state = "servo_adjust";
    next_step = offset_y < 0.0 ? "dry_run_lift_up" : "dry_run_lift_down";
  }

  out << "\"state\":" << quote(state) << ","
      << "\"next_step\":" << quote(next_step) << ","
      << "\"reason\":" << quote(reason) << ","
      << "\"target_label\":" << quote(target->label) << ","
      << "\"target_center_px\":[" << std::fixed << std::setprecision(2) << left_center.x << "," << left_center.y << "],"
      << "\"frame_size_px\":[" << static_cast<int>(frame_width) << "," << static_cast<int>(frame_height) << "],"
      << "\"offset_x_norm\":" << std::setprecision(4) << offset_x << ","
      << "\"offset_y_norm\":" << offset_y << ","
      << "\"deadband_norm\":" << deadband << ","
      << "\"requires_fresh_frame\":true,"
      << "\"metric_depth_available\":false";
  if (right_match) {
    const cv::Point2d right_center = center(right_match->bbox);
    out << ",\"horizontal_disparity_px\":" << std::setprecision(2) << left_center.x - right_center.x
        << ",\"vertical_center_delta_px\":" << std::abs(left_center.y - right_center.y);
  }
  out << "}";
  return out.str();
}

std::string build_scene_summary(const cv::Mat &left, const Quality &quality) {
  std::ostringstream out;
  out << "stereo RGB pair " << left.cols << "x" << left.rows << " captured; "
      << "mean_luma L/R=" << std::fixed << std::setprecision(2) << quality.left_mean_luma << "/" << quality.right_mean_luma << "; "
      << "pair_difference=" << quality.pair_difference << "; depth remains uncalibrated";
  return out.str();
}

std::string build_vla_context(const Options &options, const std::optional<Quality> &quality, bool has_target_observation) {
  std::ostringstream out;
  out << "two RGB cameras provide approximate depth only; operator must verify before motion";
  if (quality) {
    out << "; image_quality={"
        << "\"left\":{\"width\":" << options.width << ",\"height\":" << options.height
        << ",\"mean_luma\":" << std::fixed << std::setprecision(2) << quality->left_mean_luma
        << ",\"sharpness_proxy\":" << quality->left_sharpness << "},"
        << "\"right\":{\"width\":" << options.width << ",\"height\":" << options.height
        << ",\"mean_luma\":" << quality->right_mean_luma
        << ",\"sharpness_proxy\":" << quality->right_sharpness << "},"
        << "\"pair_difference_mean_abs\":" << quality->pair_difference << ","
        << "\"usable_for_context\":" << (quality->usable ? "true" : "false") << ","
        << "\"quality_warnings\":";
    if (quality->warning.empty()) {
      out << "[]";
    } else {
      out << "[" << quote(quality->warning) << "]";
    }
    out << "}";
  }
  if (!options.ssd_model.empty()) {
    out << "; semantic detections generated by OpenCV DNN MobileNet-SSD";
  }
  if (!options.yolox_model.empty()) {
    out << "; semantic detections generated by OpenCV DNN YOLOX ONNX";
  }
  if (options.auto_target_from_detections) {
    out << "; target_object selected from semantic detections only";
  }
  if (has_target_observation) {
    out << "; target_object has uncalibrated left/right pixel association, not metric depth";
  }
  out << "; cpp_capture_path=true";
  return out.str();
}

std::string build_payload(const Options &options,
                          const std::string &left_path,
                          const std::string &right_path,
                          const cv::Mat &left,
                          const std::vector<Detection> &detections,
                          const std::optional<Detection> &target,
                          const std::optional<Detection> &right_match,
                          const std::optional<Quality> &quality,
                          const LoopTelemetry &loop) {
  const std::string scene_summary = quality ? build_scene_summary(left, *quality) : "";
  const double confidence = quality ? (quality->usable ? 0.55 : 0.15) : 0.50;
  std::ostringstream out;
  out << "{"
      << "\"schema_version\":" << quote(kSchemaVersion) << ","
      << "\"robot_id\":" << quote(options.robot_id) << ","
      << "\"device_id\":" << quote(options.device_id) << ","
      << "\"project_id\":" << quote(options.project_id) << ","
      << "\"frame_ts_unix\":" << std::fixed << std::setprecision(6) << unix_time_seconds() << ","
      << "\"capture_loop\":{"
      << "\"loop_index\":" << loop.loop_index << ","
      << "\"loop_count\":" << loop.loop_count << ","
      << "\"interval_ms\":" << loop.interval_ms << ","
      << "\"sequence\":" << loop.sequence << ","
      << "\"frame_process_ms\":" << std::setprecision(3) << loop.frame_process_ms << ","
      << "\"loop_elapsed_ms\":" << loop.loop_elapsed_ms << ","
      << "\"implementation\":\"opencv_cpp_persistent_loop\""
      << "},"
      << "\"left_camera_id\":" << quote(options.left_camera_id) << ","
      << "\"right_camera_id\":" << quote(options.right_camera_id) << ","
      << "\"stereo_calibration_id\":" << quote(options.stereo_calibration_id) << ","
      << "\"baseline_m\":";
  if (std::isnan(options.baseline_m)) {
    out << "null";
  } else {
    out << std::setprecision(6) << options.baseline_m;
  }
  out << ",\"image_pair_ref\":{\"left_image_url\":" << quote(left_path)
      << ",\"right_image_url\":" << quote(right_path) << "},"
      << "\"detections\":" << detections_json(detections) << ","
      << "\"target_object\":" << target_json(target, right_match, options.stereo_associate_target) << ","
      << "\"pixel_servo_hint\":" << pixel_servo_hint_json(options, left, target, right_match) << ","
      << "\"estimated_depth_m\":null,"
      << "\"target_3d_camera_frame\":{},"
      << "\"scene_summary\":" << quote(scene_summary) << ","
      << "\"vla_context\":" << quote(build_vla_context(options, quality, right_match.has_value())) << ","
      << "\"confidence\":" << std::setprecision(3) << confidence << ","
      << "\"control_boundary\":" << quote(kControlBoundary)
      << "}";
  return out.str();
}

std::string shell_quote(const std::string &value) {
  std::string quoted = "'";
  for (const char c : value) {
    if (c == '\'') {
      quoted += "'\\''";
    } else {
      quoted += c;
    }
  }
  quoted += "'";
  return quoted;
}

int upload_with_curl(const Options &options, const std::string &payload) {
  const fs::path payload_path = fs::temp_directory_path() / ("rehab_stereo_context_cpp_" + std::to_string(std::time(nullptr)) + ".json");
  {
    std::ofstream out(payload_path);
    out << payload << "\n";
  }
  std::string api_base = options.api_base;
  while (!api_base.empty() && api_base.back() == '/') {
    api_base.pop_back();
  }
  const std::string url = api_base + "/api/rehab-arm/v1/devices/" + options.device_id + "/vision/stereo-context";
  std::ostringstream command;
  command << "curl -sS -f -X POST "
          << "-H 'Content-Type: application/json' ";
  if (!options.relay_token.empty()) {
    command << "-H " << shell_quote("Authorization: Bearer " + options.relay_token) << " ";
  }
  command << "--data-binary @" << shell_quote(payload_path.string()) << " " << shell_quote(url);
  const int rc = std::system(command.str().c_str());
  fs::remove(payload_path);
  return rc;
}

}  // namespace

int main(int argc, char **argv) {
  try {
    const Options options = parse_args(argc, argv);
    const auto loop_start = std::chrono::steady_clock::now();
    cv::VideoCapture left_capture = open_capture(options.left_device, options.width, options.height);
    cv::VideoCapture right_capture = open_capture(options.right_device, options.width, options.height);
    std::vector<std::string> labels;
    cv::dnn::Net net;
    if (!options.ssd_model.empty()) {
      labels = load_labels(options.ssd_labels);
      net = cv::dnn::readNetFromCaffe(options.ssd_prototxt, options.ssd_model);
    }
    std::vector<std::string> yolox_labels;
    cv::dnn::Net yolox_net;
    if (!options.yolox_model.empty()) {
      yolox_labels = load_labels(options.yolox_labels);
      yolox_net = cv::dnn::readNetFromONNX(options.yolox_model);
    }

    for (int index = 0; index < options.loop_count; ++index) {
      const auto frame_start = std::chrono::steady_clock::now();
      const int sequence = options.sequence + index;
      auto [left_path, right_path] = make_frame_paths(options, sequence);
      cv::Mat left = read_frame(left_capture, options.left_device, options.rotate_180, index == 0 ? 5 : 2);
      cv::Mat right = read_frame(right_capture, options.right_device, options.rotate_180, index == 0 ? 5 : 2);
      if (!cv::imwrite(left_path, left) || !cv::imwrite(right_path, right)) {
        throw std::runtime_error("failed to write captured stereo frames");
      }

      std::vector<Detection> detections;
      if (!options.yolox_model.empty()) {
        auto left_detections = detect_yolox(left, left_path, "left", yolox_net, yolox_labels,
                                            options.yolox_input_size, options.yolox_confidence_threshold,
                                            options.yolox_nms_threshold);
        detections.insert(detections.end(), left_detections.begin(), left_detections.end());
        if (options.detect_right_yolox) {
          auto right_detections = detect_yolox(right, right_path, "right", yolox_net, yolox_labels,
                                               options.yolox_input_size, options.yolox_confidence_threshold,
                                               options.yolox_nms_threshold);
          detections.insert(detections.end(), right_detections.begin(), right_detections.end());
        }
      }
      if (!options.ssd_model.empty()) {
      auto left_detections = detect_ssd(left, left_path, "left", net, labels, options.ssd_confidence_threshold);
      detections.insert(detections.end(), left_detections.begin(), left_detections.end());
      if (options.detect_right_ssd) {
        auto right_detections = detect_ssd(right, right_path, "right", net, labels, options.ssd_confidence_threshold);
        detections.insert(detections.end(), right_detections.begin(), right_detections.end());
      }
      }

      std::optional<Detection> target;
      if (options.auto_target_from_detections) {
        target = select_target(detections, options.target_label_allowlist);
      }
      std::optional<Detection> right_match;
      if (target && options.stereo_associate_target) {
        right_match = associate_right_detection(*target, detections, options.max_stereo_vertical_delta_px);
      }
      std::optional<Quality> quality;
      if (options.analyze_image_quality) {
        quality = analyze_quality(left, right);
      }

      const auto before_payload = std::chrono::steady_clock::now();
      LoopTelemetry loop;
      loop.loop_index = index;
      loop.loop_count = options.loop_count;
      loop.interval_ms = options.interval_ms;
      loop.sequence = sequence;
      loop.frame_process_ms = std::chrono::duration<double, std::milli>(before_payload - frame_start).count();
      loop.loop_elapsed_ms = std::chrono::duration<double, std::milli>(before_payload - loop_start).count();

      const std::string payload = build_payload(options, left_path, right_path, left, detections, target, right_match, quality, loop);
      std::cout << payload << std::endl;
      if (options.upload) {
        const int rc = upload_with_curl(options, payload);
        if (rc != 0) {
          throw std::runtime_error("curl upload failed with exit code " + std::to_string(rc));
        }
        std::cout << "\n";
      }
      if (index + 1 < options.loop_count && options.interval_ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(options.interval_ms));
      }
    }
    return 0;
  } catch (const std::exception &exc) {
    std::cerr << "stereo_camera_capture_upload_cpp: " << exc.what() << "\n";
    return 1;
  }
}
