// src/components/SetupWizard.tsx
import React, { useState, useEffect } from 'react';

interface SetupWizardProps {
  onEnvReady: () => void;
}

interface EnvData {
  os: string;
  installed: {
    docker: boolean;
    podman: boolean;
  };
  recommend: string;
  recommend_reason: string;
}

interface InstallStatus {
  status: string;
  message: string;
  progress: number;
}

export default function SetupWizard({ onEnvReady }: SetupWizardProps) {
  const [envData, setEnvData] = useState<EnvData | null>(null);
  const [selectedEngine, setSelectedEngine] = useState<string>('podman');
  const [isInstalling, setIsInstalling] = useState(false);
  const [installStatus, setInstallStatus] = useState<InstallStatus>({
    status: 'idle',
    message: '等待开始',
    progress: 0
  });
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    fetch('/api/system/env/detect')
      .then(res => res.json())
      .then(data => {
        setEnvData(data);
        setSelectedEngine(data.recommend);
      })
      .catch(error => {
        console.error('环境探测失败:', error);
        setEnvData({
          os: 'unknown',
          installed: { docker: false, podman: false },
          recommend: 'podman',
          recommend_reason: '无法探测环境，推荐使用 Podman'
        });
        setSelectedEngine('podman');
      });
  }, []);

  useEffect(() => {
    if (isInstalling && installStatus.status !== 'completed') {
      const interval = setInterval(async () => {
        try {
          const response = await fetch('/api/system/env/install/status');
          const data = await response.json();
          setInstallStatus(data);

          if (data.status === 'completed') {
            clearInterval(interval);
            setShowSuccess(true);
            setTimeout(() => {
              onEnvReady();
            }, 2000);
          } else if (data.status === 'failed') {
            clearInterval(interval);
            setIsInstalling(false);
          }
        } catch (error) {
          console.error('获取安装状态失败:', error);
        }
      }, 1000);

      return () => clearInterval(interval);
    }
  }, [isInstalling, installStatus.status, onEnvReady]);

  const handleInstall = async () => {
    if (isInstalling) return;

    setIsInstalling(true);
    setInstallStatus({
      status: 'installing',
      message: '正在启动安装...',
      progress: 0
    });

    try {
      const response = await fetch('/api/system/env/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine: selectedEngine })
      });
      const data = await response.json();
      setInstallStatus(data);
    } catch (error) {
      console.error('启动安装失败:', error);
      setInstallStatus({
        status: 'failed',
        message: '启动安装失败，请重试',
        progress: 0
      });
      setIsInstalling(false);
    }
  };

  if (showSuccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center">
        <div className="text-center">
          <div className="relative inline-block">
            <div className="w-24 h-24 bg-green-500 rounded-full flex items-center justify-center animate-bounce">
              <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          </div>
          <h1 className="mt-8 text-3xl font-bold text-green-800">环境配置完成！</h1>
          <p className="mt-4 text-green-600 text-lg">即将为您打开 PurrCat AI 助手...</p>
        </div>
      </div>
    );
  }

  if (!envData) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-amber-50 to-orange-100 flex items-center justify-center">
        <div className="text-center">
          <div className="relative">
            <div className="w-20 h-20 border-4 border-amber-800 rounded-full animate-spin border-t-transparent"></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 bg-amber-500 rounded-full"></div>
            </div>
          </div>
          <p className="mt-6 text-amber-800 font-bold text-xl">探测环境运行中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-amber-50 via-orange-50 to-yellow-100 flex items-center justify-center p-8">
      <div className="max-w-lg w-full">
        <div className="text-center mb-12">
          <div className="relative inline-block">
            <div className="w-24 h-24 bg-gradient-to-br from-amber-400 to-orange-500 rounded-full flex items-center justify-center shadow-lg">
              <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                <span className="text-3xl">🐱</span>
              </div>
            </div>
          </div>
          <h1 className="mt-6 text-3xl font-bold text-amber-900">配置 AI 沙盒环境</h1>
        </div>

        <div className="bg-white rounded-3xl shadow-xl p-8 border-4 border-amber-200">
          <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-blue-800 text-sm">💡 {envData.recommend_reason}</p>
            </div>
          </div>

          <div className="space-y-4 mb-8">
            <label className={`block p-4 border-2 rounded-xl cursor-pointer transition-all duration-200 ${
              selectedEngine === 'podman' 
                ? 'border-blue-500 bg-blue-50 shadow-md' 
                : 'border-gray-200 hover:border-gray-300'
            }`}>
              <div className="flex items-center">
                <input 
                  type="radio" 
                  name="engine" 
                  value="podman"
                  checked={selectedEngine === 'podman'}
                  onChange={(e) => setSelectedEngine(e.target.value)}
                  className="w-5 h-5 text-blue-600 cursor-pointer"
                />
                <span className="ml-4 font-semibold text-gray-800">使用 Podman (静默极速版)</span>
                {envData.recommend === 'podman' && (
                  <span className="ml-3 px-3 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full">
                    系统推荐
                  </span>
                )}
                {envData.installed.podman && (
                  <span className="ml-3 px-3 py-1 bg-gray-100 text-gray-600 text-xs font-semibold rounded-full">
                    已安装
                  </span>
                )}
              </div>
              <p className="ml-9 mt-2 text-sm text-gray-500">
                无需繁杂的图形界面，体积小巧，自动在后台配置轻量级虚拟机。推荐 Windows 用户使用。
              </p>
            </label>

            <label className={`block p-4 border-2 rounded-xl cursor-pointer transition-all duration-200 ${
              selectedEngine === 'docker' 
                ? 'border-blue-500 bg-blue-50 shadow-md' 
                : 'border-gray-200 hover:border-gray-300'
            }`}>
              <div className="flex items-center">
                <input 
                  type="radio" 
                  name="engine" 
                  value="docker"
                  checked={selectedEngine === 'docker'}
                  onChange={(e) => setSelectedEngine(e.target.value)}
                  className="w-5 h-5 text-blue-600 cursor-pointer"
                />
                <span className="ml-4 font-semibold text-gray-800">使用传统 Docker</span>
                {envData.recommend === 'docker' && (
                  <span className="ml-3 px-3 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full">
                    系统推荐
                  </span>
                )}
                {envData.installed.docker && (
                  <span className="ml-3 px-3 py-1 bg-gray-100 text-gray-600 text-xs font-semibold rounded-full">
                    已安装
                  </span>
                )}
              </div>
              <p className="ml-9 mt-2 text-sm text-gray-500">
                业界标准容器引擎。如果选择此项但未安装，您可能需要手动前往官网下载 Docker Desktop 约 500MB 的安装包。
              </p>
            </label>
          </div>

          {installStatus.status === 'failed' && (
            <div className="mb-6 p-4 bg-red-100 rounded-xl border-2 border-red-300">
              <div className="flex items-center gap-2 text-red-700">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="font-bold">安装失败</span>
              </div>
              <p className="mt-2 text-red-600 text-sm">{installStatus.message}</p>
            </div>
          )}

          {isInstalling && installStatus.status !== 'failed' && (
            <div className="mb-6">
              <div className="flex justify-between items-center mb-2">
                <span className="text-amber-800 font-medium">{installStatus.message}</span>
                <span className="text-amber-800 font-bold">{installStatus.progress}%</span>
              </div>
              <div className="h-4 bg-amber-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-500 ease-out"
                  style={{ width: `${installStatus.progress}%` }}
                />
              </div>
            </div>
          )}

          <button
            onClick={handleInstall}
            disabled={isInstalling && installStatus.status !== 'failed'}
            className={`w-full py-4 rounded-2xl font-bold text-lg transition-all duration-300 transform ${
              isInstalling && installStatus.status !== 'failed'
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed scale-100'
                : 'bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:from-amber-600 hover:to-orange-600 hover:scale-[1.02] shadow-lg hover:shadow-xl'
            }`}
          >
            {isInstalling && installStatus.status !== 'failed' ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                安装中...
              </span>
            ) : installStatus.status === 'failed' ? (
              '重试安装'
            ) : (
              '确定并初始化环境'
            )}
          </button>

          <p className="mt-4 text-center text-gray-500 text-sm">
            安装过程需要联网，可能需要 1-3 分钟，请耐心等待
          </p>
        </div>
      </div>
    </div>
  );
}