#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#include <opencv2/dnn.hpp>
#include <opencv2/opencv.hpp>

struct Detection {
    std::string label;
    std::string source;
    double confidence{0.0};
    cv::Rect2f box;
};

static std::string gTargetLoadError;
static std::string gGripperLoadError;

static std::string envText(const char* key, const std::string& fallback = "") {
    const char* value = std::getenv(key);
    return value && *value ? std::string(value) : fallback;
}

static double envDouble(const char* key, double fallback) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return fallback;
    }
    try {
        return std::stod(value);
    } catch (...) {
        return fallback;
    }
}

static int envInt(const char* key, int fallback) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return fallback;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return fallback;
    }
}

static std::string jsonEscape(const std::string& text) {
    std::ostringstream out;
    for (char ch : text) {
        if (ch == '"' || ch == '\\') {
            out << '\\' << ch;
        } else if (ch == '\n') {
            out << "\\n";
        } else if (ch == '\r') {
            out << "\\r";
        } else if (ch == '\t') {
            out << "\\t";
        } else {
            out << ch;
        }
    }
    return out.str();
}

static cv::Mat flipFrame(const cv::Mat& frame, const std::string& mode) {
    if (mode == "none" || mode.empty()) {
        return frame.clone();
    }
    cv::Mat flipped;
    if (mode == "h") {
        cv::flip(frame, flipped, 1);
    } else if (mode == "v") {
        cv::flip(frame, flipped, 0);
    } else if (mode == "hv") {
        cv::flip(frame, flipped, -1);
    } else {
        std::cerr << "unknown flip mode '" << mode << "', using none\n";
        return frame.clone();
    }
    return flipped;
}

static bool openCamera(cv::VideoCapture& cap, const std::string& device, int width, int height) {
    cap.open(device, cv::CAP_V4L2);
    if (!cap.isOpened()) {
        return false;
    }
    cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap.set(cv::CAP_PROP_FRAME_WIDTH, width);
    cap.set(cv::CAP_PROP_FRAME_HEIGHT, height);
    cv::Mat frame;
    return cap.read(frame) && !frame.empty();
}

static std::vector<std::vector<float>> rowsFromYoloOutput(const cv::Mat& output) {
    std::vector<std::vector<float>> rows;
    if (output.empty()) {
        return rows;
    }
    const float* data = reinterpret_cast<const float*>(output.data);
    if (output.dims == 3) {
        const int a = output.size[1];
        const int b = output.size[2];
        if ((a == 84 || a == 85 || a == 5 || a == 6) && b > a) {
            rows.reserve(static_cast<size_t>(b));
            for (int i = 0; i < b; ++i) {
                std::vector<float> row(static_cast<size_t>(a));
                for (int j = 0; j < a; ++j) {
                    row[static_cast<size_t>(j)] = data[j * b + i];
                }
                rows.push_back(std::move(row));
            }
        } else {
            rows.reserve(static_cast<size_t>(a));
            for (int i = 0; i < a; ++i) {
                std::vector<float> row(static_cast<size_t>(b));
                for (int j = 0; j < b; ++j) {
                    row[static_cast<size_t>(j)] = data[i * b + j];
                }
                rows.push_back(std::move(row));
            }
        }
    } else if (output.dims == 2) {
        const int a = output.size[0];
        const int b = output.size[1];
        if ((a == 84 || a == 85 || a == 5 || a == 6) && b > a) {
            rows.reserve(static_cast<size_t>(b));
            for (int i = 0; i < b; ++i) {
                std::vector<float> row(static_cast<size_t>(a));
                for (int j = 0; j < a; ++j) {
                    row[static_cast<size_t>(j)] = data[j * b + i];
                }
                rows.push_back(std::move(row));
            }
        } else {
            rows.reserve(static_cast<size_t>(a));
            for (int i = 0; i < a; ++i) {
                std::vector<float> row(static_cast<size_t>(b));
                for (int j = 0; j < b; ++j) {
                    row[static_cast<size_t>(j)] = data[i * b + j];
                }
                rows.push_back(std::move(row));
            }
        }
    }
    return rows;
}

static cv::Mat forwardYolo(cv::dnn::Net& net, const cv::Mat& frame, int inputSize) {
    cv::Mat blob = cv::dnn::blobFromImage(frame, 1.0 / 255.0, cv::Size(inputSize, inputSize), cv::Scalar(), true, false, CV_32F);
    net.setInput(blob);
    return net.forward();
}

static std::vector<Detection> nmsDetections(const std::vector<Detection>& detections, float threshold) {
    if (detections.empty()) {
        return {};
    }
    std::vector<cv::Rect> boxes;
    std::vector<float> scores;
    boxes.reserve(detections.size());
    scores.reserve(detections.size());
    for (const auto& det : detections) {
        boxes.emplace_back(
            static_cast<int>(std::round(det.box.x)),
            static_cast<int>(std::round(det.box.y)),
            static_cast<int>(std::round(det.box.width)),
            static_cast<int>(std::round(det.box.height)));
        scores.push_back(static_cast<float>(det.confidence));
    }
    std::vector<int> keep;
    cv::dnn::NMSBoxes(boxes, scores, 0.0f, threshold, keep);
    std::vector<Detection> result;
    for (int index : keep) {
        result.push_back(detections[static_cast<size_t>(index)]);
    }
    std::sort(result.begin(), result.end(), [](const Detection& a, const Detection& b) { return a.confidence > b.confidence; });
    return result;
}

static std::pair<std::optional<Detection>, std::string> detectTarget(
    cv::dnn::Net* net,
    const cv::Mat& frame,
    const std::string& modelPath,
    int inputSize,
    double conf) {
    if (!net || modelPath.empty() || !std::filesystem::is_regular_file(modelPath)) {
        if (!gTargetLoadError.empty()) {
            return {std::nullopt, "\"state\":\"opencv_dnn_model_load_error\",\"model_path\":\"" + jsonEscape(modelPath) + "\",\"error\":\"" + jsonEscape(gTargetLoadError) + "\""};
        }
        return {std::nullopt, "\"state\":\"target_model_missing\",\"model_path\":\"" + jsonEscape(modelPath) + "\""};
    }
    const double minWidth = envDouble("REHAB_TARGET_MIN_WIDTH_PX", 40.0);
    const double minHeight = envDouble("REHAB_TARGET_MIN_HEIGHT_PX", 50.0);
    cv::Mat output = forwardYolo(*net, frame, inputSize);
    auto rows = rowsFromYoloOutput(output);
    const double scaleX = static_cast<double>(frame.cols) / inputSize;
    const double scaleY = static_cast<double>(frame.rows) / inputSize;
    std::vector<Detection> candidates;
    int lowConf = 0;
    int tooSmall = 0;
    for (const auto& row : rows) {
        if (row.size() < 84) {
            continue;
        }
        const bool yolo5 = row.size() >= 85;
        const float obj = yolo5 ? row[4] : 1.0f;
        const int scoreOffset = yolo5 ? 5 : 4;
        int bestClass = -1;
        float bestScore = 0.0f;
        for (int cls = 0; cls < 80 && scoreOffset + cls < static_cast<int>(row.size()); ++cls) {
            if (row[static_cast<size_t>(scoreOffset + cls)] > bestScore) {
                bestScore = row[static_cast<size_t>(scoreOffset + cls)];
                bestClass = cls;
            }
        }
        if (bestClass != 39 && bestClass != 41) {
            continue;
        }
        const double score = static_cast<double>(obj * bestScore);
        if (score < conf) {
            ++lowConf;
            continue;
        }
        const double cx = row[0];
        const double cy = row[1];
        const double bw = row[2];
        const double bh = row[3];
        double x = std::clamp((cx - bw / 2.0) * scaleX, 0.0, static_cast<double>(frame.cols - 1));
        double y = std::clamp((cy - bh / 2.0) * scaleY, 0.0, static_cast<double>(frame.rows - 1));
        double width = std::clamp(bw * scaleX, 1.0, static_cast<double>(frame.cols) - x);
        double height = std::clamp(bh * scaleY, 1.0, static_cast<double>(frame.rows) - y);
        if (width < minWidth || height < minHeight) {
            ++tooSmall;
            continue;
        }
        candidates.push_back(Detection{bestClass == 39 ? "target_bottle" : "target_cup",
                                       yolo5 ? "opencv_dnn_yolov5_coco_target_detector" : "opencv_dnn_yolo11_coco_target_detector",
                                       score,
                                       cv::Rect2f(static_cast<float>(x), static_cast<float>(y), static_cast<float>(width), static_cast<float>(height))});
    }
    auto accepted = nmsDetections(candidates, 0.45f);
    std::ostringstream gate;
    gate << "\"state\":\"" << (accepted.empty() ? "no_yolo_cup_or_bottle" : "candidate_accepted") << "\",";
    gate << "\"detector\":\"opencv_dnn_pretrained_yolo_coco_target_detector\",";
    gate << "\"model_path\":\"" << jsonEscape(modelPath) << "\",";
    gate << "\"accepted_count\":" << accepted.size() << ",";
    gate << "\"candidate_count\":" << candidates.size() << ",";
    gate << "\"rejected_low_confidence\":" << lowConf << ",";
    gate << "\"rejected_too_small\":" << tooSmall << ",";
    gate << "\"min_confidence\":" << conf << ",";
    gate << "\"min_size_px\":[" << minWidth << "," << minHeight << "],";
    gate << "\"target_classes\":[\"target_bottle\",\"target_cup\"]";
    if (accepted.empty()) {
        return {std::nullopt, gate.str()};
    }
    return {accepted.front(), gate.str()};
}

static std::vector<Detection> detectGripper(
    cv::dnn::Net* net,
    const cv::Mat& frame,
    const std::string& modelPath,
    int inputSize,
    double conf) {
    if (!net || modelPath.empty() || !std::filesystem::is_regular_file(modelPath)) {
        return {};
    }
    cv::Mat output = forwardYolo(*net, frame, inputSize);
    auto rows = rowsFromYoloOutput(output);
    const double scaleX = static_cast<double>(frame.cols) / inputSize;
    const double scaleY = static_cast<double>(frame.rows) / inputSize;
    const std::string singleLabel = envText("REHAB_END_EFFECTOR_SINGLE_CLASS_LABEL", "gripper_tip");
    std::vector<Detection> candidates;
    for (const auto& row : rows) {
        if (row.size() < 5) {
            continue;
        }
        std::string label = singleLabel;
        double score = row[4];
        if (row.size() >= 6) {
            const double c1 = row[4];
            const double c2 = row[5];
            label = c1 >= c2 ? "end_effector" : "gripper_tip";
            score = std::max(c1, c2);
        }
        if (score < conf) {
            continue;
        }
        const double cx = row[0];
        const double cy = row[1];
        const double bw = row[2];
        const double bh = row[3];
        if (cx < 0 || cy < 0 || bw < 8 || bh < 8 || cx > inputSize || cy > inputSize) {
            continue;
        }
        double x = std::clamp((cx - bw / 2.0) * scaleX, 0.0, static_cast<double>(frame.cols - 1));
        double y = std::clamp((cy - bh / 2.0) * scaleY, 0.0, static_cast<double>(frame.rows - 1));
        double width = std::clamp(bw * scaleX, 1.0, static_cast<double>(frame.cols) - x);
        double height = std::clamp(bh * scaleY, 1.0, static_cast<double>(frame.rows) - y);
        const double aspect = height / std::max(1.0, width);
        if (label == "gripper_tip" && !(0.7 <= aspect && aspect <= 2.8)) {
            continue;
        }
        if (label == "end_effector" && !(0.5 <= aspect && aspect <= 5.5)) {
            continue;
        }
        candidates.push_back(Detection{label, "opencv_dnn_gripper_yolo", score, cv::Rect2f(static_cast<float>(x), static_cast<float>(y), static_cast<float>(width), static_cast<float>(height))});
    }
    auto accepted = nmsDetections(candidates, 0.45f);
    if (accepted.size() > 1) {
        accepted.resize(1);
    }
    return accepted;
}

static void drawDetection(cv::Mat& frame, const Detection& det, const cv::Scalar& color) {
    cv::rectangle(frame, det.box, color, 2);
    std::ostringstream label;
    label << det.label << " " << std::fixed << std::setprecision(2) << det.confidence;
    const int textY = std::max(18, static_cast<int>(det.box.y) - 7);
    cv::putText(frame, label.str(), cv::Point(static_cast<int>(det.box.x), textY), cv::FONT_HERSHEY_SIMPLEX, 0.52, color, 2);
}

static std::string detectionJson(const Detection& det) {
    const double cx = det.box.x + det.box.width / 2.0;
    const double cy = det.box.y + det.box.height / 2.0;
    std::ostringstream out;
    out << "{\"label\":\"" << jsonEscape(det.label) << "\",";
    if (det.label == "target_bottle") {
        out << "\"coco_label\":\"bottle\",";
    } else if (det.label == "target_cup") {
        out << "\"coco_label\":\"cup\",";
    }
    out << "\"confidence\":" << std::fixed << std::setprecision(4) << det.confidence << ",";
    out << "\"bbox_xywh\":[" << std::setprecision(2) << det.box.x << "," << det.box.y << "," << det.box.width << "," << det.box.height << "],";
    out << "\"center_px\":[" << cx << "," << cy << "],";
    out << "\"source\":\"" << jsonEscape(det.source) << "\"}";
    return out.str();
}

static void writeText(const std::string& path, const std::string& text) {
    std::ofstream file(path);
    file << text;
}

static std::string targetPayload(const std::optional<Detection>& target, const std::string& gateJson) {
    std::ostringstream out;
    out << "{\n  \"target\":";
    out << (target ? detectionJson(*target) : "null");
    out << ",\n  \"quality_gate\":{\"schema_version\":\"target_quality_gate_v2\",";
    out << gateJson << ",";
    out << "\"control_boundary\":\"target_quality_gate_only_not_motion_permission\"}\n}";
    return out.str();
}

static std::string gripperPayload(const std::vector<Detection>& detections, int width, int height, int inputSize, double conf) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"output_shape\":[1,5,3549],\n";
    out << "  \"confidence_threshold\":" << conf << ",\n";
    out << "  \"frame_size_px\":[" << width << "," << height << "],\n";
    out << "  \"input_size_px\":" << inputSize << ",\n";
    out << "  \"confidence_transform\":\"raw\",\n";
    out << "  \"detections\":[";
    for (size_t i = 0; i < detections.size(); ++i) {
        if (i) {
            out << ",";
        }
        out << detectionJson(detections[i]);
    }
    out << "]\n}";
    return out.str();
}

static std::string probeContext(double processMs, int width, int height, const std::optional<Detection>& leftTarget) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"schema_version\":\"vla_cpp_dnn_probe_v1\",\n";
    out << "  \"frame_size_px\":[" << width << "," << height << "],\n";
    out << "  \"process_ms\":" << std::fixed << std::setprecision(3) << processMs << ",\n";
    out << "  \"target_object\":" << (leftTarget ? detectionJson(*leftTarget) : "null") << ",\n";
    out << "  \"control_boundary\":\"vision_probe_only_not_motion_permission\"\n";
    out << "}\n";
    return out.str();
}

int main(int argc, char** argv) {
    const std::string leftDev = argc > 1 ? argv[1] : "/dev/video45";
    const std::string rightDev = argc > 2 ? argv[2] : "/dev/video47";
    const std::string outDir = argc > 3 ? argv[3] : "/tmp/rehab_vla_cpp_probe";
    const std::string leftFlip = argc > 4 ? argv[4] : "none";
    const std::string rightFlip = argc > 5 ? argv[5] : leftFlip;
    const int width = 640;
    const int height = 480;
    std::filesystem::create_directories(outDir);

    cv::VideoCapture left, right;
    const bool monoFallback = leftDev == rightDev;
    if (!openCamera(left, leftDev, width, height) || (!monoFallback && !openCamera(right, rightDev, width, height))) {
        std::cerr << "failed to open readable stereo cameras: " << leftDev << " " << rightDev << "\n";
        return 2;
    }

    const std::string targetModel = envText("REHAB_TARGET_ONNX", "/home/pi/rehab_arm_models/yolo/yolo11s.onnx");
    const std::string gripperModel = envText("REHAB_END_EFFECTOR_ONNX", "/home/pi/rehab_vla/gripper_yolo11n_416_e7.onnx");
    const int targetSize = envInt("REHAB_TARGET_IMGSZ", 640);
    const int gripperSize = envInt("REHAB_END_EFFECTOR_IMGSZ", 416);
    const double targetConf = envDouble("REHAB_TARGET_CONF", 0.45);
    const double gripperConf = envDouble("REHAB_END_EFFECTOR_CONF", 0.45);

    cv::dnn::Net targetNet;
    cv::dnn::Net gripperNet;
    cv::dnn::Net* targetNetPtr = nullptr;
    cv::dnn::Net* gripperNetPtr = nullptr;
    if (std::filesystem::is_regular_file(targetModel)) {
        try {
            targetNet = cv::dnn::readNetFromONNX(targetModel);
            targetNet.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
            targetNet.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
            targetNetPtr = &targetNet;
        } catch (const cv::Exception& exc) {
            gTargetLoadError = exc.what();
            std::cerr << "failed to load target DNN model: " << exc.what() << "\n";
        }
    }
    if (std::filesystem::is_regular_file(gripperModel)) {
        try {
            gripperNet = cv::dnn::readNetFromONNX(gripperModel);
            gripperNet.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);
            gripperNet.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
            gripperNetPtr = &gripperNet;
        } catch (const cv::Exception& exc) {
            gGripperLoadError = exc.what();
            std::cerr << "failed to load gripper DNN model: " << exc.what() << "\n";
        }
    }

    cv::Mat leftFrame, rightFrame;
    const auto start = std::chrono::steady_clock::now();
    if (!left.read(leftFrame) || leftFrame.empty()) {
        std::cerr << "failed to read left frame\n";
        return 3;
    }
    if (monoFallback) {
        rightFrame = leftFrame.clone();
    } else if (!right.read(rightFrame) || rightFrame.empty()) {
        std::cerr << "failed to read right frame\n";
        return 3;
    }
    leftFrame = flipFrame(leftFrame, leftFlip);
    rightFrame = flipFrame(rightFrame, rightFlip);

    std::optional<Detection> leftTarget;
    std::optional<Detection> rightTarget;
    std::string leftGate = "\"state\":\"detector_not_run\"";
    std::string rightGate = "\"state\":\"detector_not_run\"";
    std::vector<Detection> grippers;
    try {
        auto leftResult = detectTarget(targetNetPtr, leftFrame, targetModel, targetSize, targetConf);
        leftTarget = leftResult.first;
        leftGate = leftResult.second;
        auto rightResult = detectTarget(targetNetPtr, rightFrame, targetModel, targetSize, targetConf);
        rightTarget = rightResult.first;
        rightGate = rightResult.second;
        grippers = detectGripper(gripperNetPtr, leftFrame, gripperModel, gripperSize, gripperConf);
    } catch (const cv::Exception& exc) {
        leftGate = "\"state\":\"opencv_dnn_runtime_error\",\"error\":\"" + jsonEscape(exc.what()) + "\"";
        rightGate = leftGate;
        std::cerr << "DNN inference failed: " << exc.what() << "\n";
    }

    if (leftTarget) {
        drawDetection(leftFrame, *leftTarget, cv::Scalar(0, 220, 255));
    }
    if (rightTarget) {
        drawDetection(rightFrame, *rightTarget, cv::Scalar(0, 220, 255));
    }
    for (const auto& det : grippers) {
        drawDetection(leftFrame, det, cv::Scalar(255, 190, 40));
    }

    const auto end = std::chrono::steady_clock::now();
    const double processMs = std::chrono::duration<double, std::milli>(end - start).count();
    cv::imwrite(outDir + "/latest_left.jpg", leftFrame, {cv::IMWRITE_JPEG_QUALITY, 76});
    cv::imwrite(outDir + "/latest_right.jpg", rightFrame, {cv::IMWRITE_JPEG_QUALITY, 70});
    writeText(outDir + "/latest_context.json", probeContext(processMs, leftFrame.cols, leftFrame.rows, leftTarget));
    writeText(outDir + "/latest_target_context.json", targetPayload(leftTarget, leftGate));
    writeText(outDir + "/latest_target_context_right.json", targetPayload(rightTarget, rightGate));
    writeText(outDir + "/latest_ort_context.json", gripperPayload(grippers, leftFrame.cols, leftFrame.rows, gripperSize, gripperConf));

    std::cout << "cpp_dnn=true process_ms=" << processMs
              << " target_left=" << (leftTarget ? "1" : "0")
              << " target_right=" << (rightTarget ? "1" : "0")
              << " gripper=" << grippers.size()
              << " out=" << outDir << "\n";
    return 0;
}
