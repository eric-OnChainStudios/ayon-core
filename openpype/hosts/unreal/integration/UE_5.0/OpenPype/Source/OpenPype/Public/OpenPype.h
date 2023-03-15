// Copyright 2023, Ayon, All rights reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#include "Widgets/SWidget.h"
#include "Framework/Commands/UICommandList.h"
#include "IWebSocket.h"


class FOpenPypeModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

protected:
	static TSharedRef<SWidget> GenerateOpenPypeMenuContent(TSharedRef<class FUICommandList> InCommandList);

	static void CallMethod(const FString MethodName, const TArray<FString> Args);

private:
	void RegisterMenus();
    void RegisterSettings();
	bool HandleSettingsSaved();
	void RegisterOpenPypeMenu();
	void MapCommands();

private:
	TSharedPtr<class FUICommandList> OpenPypeCommands;
};
