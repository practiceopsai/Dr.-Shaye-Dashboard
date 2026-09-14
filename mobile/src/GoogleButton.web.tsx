import React from 'react';
import { Button } from './ui';
export function GoogleButton({ onPress }: { onPress: () => void; disabled: boolean }) {
  return <Button label="Sign in with Google" secondary icon="logo-google" disabled onPress={onPress} />;
}
