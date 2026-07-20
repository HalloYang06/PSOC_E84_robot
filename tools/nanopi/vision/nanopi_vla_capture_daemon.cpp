#include <atomic>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <opencv2/opencv.hpp>

static std::atomic<bool> running{true};

static void handleSignal(int) {
    running = false;
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

static std::vector<float> buildTensorCHW(const cv::Mat& frame, int targetSize) {
    cv::Mat resized;
    cv::resize(frame, resized, cv::Size(targetSize, targetSize));
    cv::Mat rgb;
    cv::cvtColor(resized, rgb, cv::COLOR_BGR2RGB);
    rgb.convertTo(rgb, CV_32F, 1.0 / 255.0);
    std::vector<float> tensor(static_cast<size_t>(3 * targetSize * targetSize));
    std::vector<cv::Mat> channels;
    cv::split(rgb, channels);
    for (int c = 0; c < 3; ++c) {
        const float* ptr = channels[c].ptr<float>(0);
        std::copy(ptr, ptr + targetSize * targetSize, tensor.begin() + static_cast<size_t>(c * targetSize * targetSize));
    }
    return tensor;
}

static void writeTextAtomic(const std::filesystem::path& path, const std::string& text) {
    auto tmp = path;
    tmp += ".tmp";
    {
        std::ofstream out(tmp);
        out << text;
    }
    std::filesystem::rename(tmp, path);
}

static void writeBinaryAtomic(const std::filesystem::path& path, const std::vector<float>& tensor) {
    auto tmp = path;
    tmp += ".tmp";
    {
        std::ofstream out(tmp, std::ios::binary);
        out.write(reinterpret_cast<const char*>(tensor.data()), static_cast<std::streamsize>(tensor.size() * sizeof(float)));
    }
    std::filesystem::rename(tmp, path);
}

int main(int argc, char** argv) {
    std::signal(SIGTERM, handleSignal);
    std::signal(SIGINT, handleSignal);

    const std::string leftDev = argc > 1 ? argv[1] : "/dev/video45";
    const std::string rightDev = argc > 2 ? argv[2] : "/dev/video47";
    const std::filesystem::path outDir = argc > 3 ? argv[3] : "/home/pi/rehab_vla_frames";
    const std::string leftFlip = argc > 4 ? argv[4] : "none";
    const std::string rightFlip = argc > 5 ? argv[5] : leftFlip;
    const double fps = argc > 6 ? std::stod(argv[6]) : 4.0;
    const int width = 640;
    const int height = 480;
    std::filesystem::create_directories(outDir);

    cv::VideoCapture left;
    cv::VideoCapture right;
    const bool monoFallback = leftDev == rightDev;
    if (!openCamera(left, leftDev, width, height) || (!monoFallback && !openCamera(right, rightDev, width, height))) {
        std::cerr << "failed to open readable stereo cameras: " << leftDev << " " << rightDev << std::endl;
        return 2;
    }

    uint64_t frameIndex = 0;
    const auto period = std::chrono::duration<double>(1.0 / std::max(0.1, fps));
    while (running) {
        const auto loopStart = std::chrono::steady_clock::now();
        cv::Mat leftFrame;
        cv::Mat rightFrame;
        if (!left.read(leftFrame) || leftFrame.empty()) {
            std::cerr << "failed to read left frame" << std::endl;
            break;
        }
        if (monoFallback) {
            rightFrame = leftFrame.clone();
        } else if (!right.read(rightFrame) || rightFrame.empty()) {
            std::cerr << "failed to read right frame" << std::endl;
            break;
        }
        leftFrame = flipFrame(leftFrame, leftFlip);
        rightFrame = flipFrame(rightFrame, rightFlip);

        auto tensor = buildTensorCHW(leftFrame, 416);
        cv::imwrite((outDir / "latest_left.tmp.jpg").string(), leftFrame, {cv::IMWRITE_JPEG_QUALITY, 62});
        cv::imwrite((outDir / "latest_right.tmp.jpg").string(), rightFrame, {cv::IMWRITE_JPEG_QUALITY, 52});
        std::filesystem::rename(outDir / "latest_left.tmp.jpg", outDir / "latest_left.jpg");
        std::filesystem::rename(outDir / "latest_right.tmp.jpg", outDir / "latest_right.jpg");
        writeBinaryAtomic(outDir / "latest_tensor_chw_fp32.bin", tensor);

        const auto loopEnd = std::chrono::steady_clock::now();
        const double processMs = std::chrono::duration<double, std::milli>(loopEnd - loopStart).count();
        ++frameIndex;
        std::string json =
            "{\n"
            "  \"schema_version\":\"vla_cpp_capture_daemon_v1\",\n"
            "  \"frame_size_px\":[640,480],\n"
            "  \"capture_daemon_frame_index\":" + std::to_string(frameIndex) + ",\n"
            "  \"process_ms\":" + std::to_string(processMs) + ",\n"
            "  \"target_object\":null,\n"
            "  \"control_boundary\":\"vision_capture_only_not_motion_permission\"\n"
            "}\n";
        writeTextAtomic(outDir / "latest_context.json", json);
        std::cout << "capture_daemon frame=" << frameIndex << " process_ms=" << processMs << std::endl;

        const auto elapsed = std::chrono::steady_clock::now() - loopStart;
        if (elapsed < period) {
            std::this_thread::sleep_for(std::chrono::duration_cast<std::chrono::milliseconds>(period - elapsed));
        }
    }
    return 0;
}
