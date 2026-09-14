import React from 'react';
import { GoogleSigninButton } from '@react-native-google-signin/google-signin';

export function GoogleButton({ onPress, disabled }: { onPress: () => void; disabled: boolean }) {
  return <GoogleSigninButton
    accessibilityLabel="Sign in with Google"
    style={{ width: '100%', height: 48 }}
    size={GoogleSigninButton.Size.Wide}
    color={GoogleSigninButton.Color.Light}
    disabled={disabled}
    onPress={onPress}
  />;
}
